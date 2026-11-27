use std::{env, net::{SocketAddr, TcpListener as StdTcpListener}, sync::{Arc, atomic::{AtomicU64, Ordering}}, time::Duration};
use socket2::{Domain, Protocol, Socket, Type};
use tokio::{io::{AsyncReadExt, AsyncWriteExt, BufReader}, net::{TcpListener, TcpStream}, sync::Semaphore, time::{sleep, sleep_until, timeout, Instant}};

const MAX_BUFFER: usize = 256 * 1024;
const READ_CHUNK: usize = 64 * 1024;
const CONTROL_TIMEOUT: Duration = Duration::from_secs(2);
const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
static NEXT_ID: AtomicU64 = AtomicU64::new(1);

fn policy_allows(response: &str) -> bool {
    let Some(body) = response.strip_suffix('\n') else { return false; };
    let mut fields = body.split(' ');
    matches!((fields.next(), fields.next(), fields.next()),
        (Some("ALLOW"), Some(generation), None) if generation.parse::<u64>().is_ok())
}

fn audit_acknowledged(response: &[u8]) -> bool {
    response == b"OK\n"
}

#[derive(Clone)]
struct Config { upstream: SocketAddr, policy: SocketAddr, revalidate: Duration, idle: Duration }

async fn policy(config: &Config, id: u64) -> std::io::Result<bool> {
    timeout(CONTROL_TIMEOUT, async {
        let stream = TcpStream::connect(config.policy).await?;
        let (read, mut write) = stream.into_split();
        write.write_all(format!("CHECK {id}\n").as_bytes()).await?;
        let mut reader = BufReader::new(read);
        // A u64 generation needs at most 21 bytes plus the verb and newline.
        // The fixed cap also bounds memory if the control peer misbehaves.
        let mut answer = [0u8; 32];
        let mut len = 0;
        while len < answer.len() {
            let byte = reader.read_u8().await?;
            answer[len] = byte;
            len += 1;
            if byte == b'\n' {
                break;
            }
        }
        Ok(std::str::from_utf8(&answer[..len])
            .map(policy_allows)
            .unwrap_or(false))
    }).await.map_err(|_| std::io::Error::new(std::io::ErrorKind::TimedOut, "policy control timeout"))?
}

async fn audit(config: &Config, id: u64, event: &str, up: u64, down: u64) -> bool {
    match timeout(CONTROL_TIMEOUT, async {
        let stream = TcpStream::connect(config.policy).await?;
        let (read, mut write) = stream.into_split();
        write.write_all(format!("AUDIT {id} {event} {up} {down}\n").as_bytes()).await?;
        let mut reader = BufReader::new(read);
        let mut ack = [0u8; 3];
        reader.read_exact(&mut ack).await?;
        Ok::<bool, std::io::Error>(audit_acknowledged(&ack))
    }).await {
        Ok(Ok(acknowledged)) => acknowledged,
        _ => false,
    }
}

async fn relay(client: TcpStream, config: Config) -> std::io::Result<()> {
    let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
    if !policy(&config, id).await? { let _ = audit(&config, id, "denied", 0, 0).await; return Ok(()); }
    let upstream = match timeout(CONNECT_TIMEOUT, TcpStream::connect(config.upstream)).await {
        Ok(Ok(s)) => s,
        Ok(Err(e)) => { let _ = audit(&config, id, "connect_failed", 0, 0).await; return Err(e); }
        Err(_) => { let _ = audit(&config, id, "connect_failed", 0, 0).await; return Ok(()); }
    };
    client.set_nodelay(true)?;
    upstream.set_nodelay(true)?;
    if !audit(&config, id, "connected", 0, 0).await { return Ok(()); }

    let mut c2u = Vec::with_capacity(MAX_BUFFER);
    let mut u2c = Vec::with_capacity(MAX_BUFFER);
    let (mut cr, mut cw) = client.into_split();
    let (mut ur, mut uw) = upstream.into_split();
    let mut tmp_c = [0u8; READ_CHUNK];
    let mut tmp_u = [0u8; READ_CHUNK];
    let (mut c2u_off, mut u2c_off) = (0usize, 0usize);
    let (mut client_read, mut upstream_read, mut client_write, mut upstream_write) = (true, true, true, true);
    let (mut up_bytes, mut down_bytes) = (0u64, 0u64);
    let mut next_check = Instant::now() + config.revalidate;
    let mut last_data = Instant::now();
    let mut event = "closed";

    loop {
        if !client_read && !upstream_read && c2u_off == c2u.len() && u2c_off == u2c.len() { break; }
        if Instant::now().duration_since(last_data) >= config.idle { event = "timeout"; break; }
        tokio::select! {
            result = cr.read(&mut tmp_c[..(MAX_BUFFER - (c2u.len() - c2u_off)).min(READ_CHUNK)]), if client_read && c2u.len() - c2u_off < MAX_BUFFER => {
                match result {
                    Ok(0) => { client_read = false; if c2u_off == c2u.len() && upstream_write { let _ = uw.shutdown().await; upstream_write = false; } },
                    Ok(n) => { if c2u_off == c2u.len() { c2u.clear(); c2u_off = 0; } else if c2u_off > 0 { let remaining = c2u.len() - c2u_off; c2u.copy_within(c2u_off.., 0); c2u.truncate(remaining); c2u_off = 0; } c2u.extend_from_slice(&tmp_c[..n]); last_data = Instant::now(); },
                    Err(_) => break,
                }
            }
            result = ur.read(&mut tmp_u[..(MAX_BUFFER - (u2c.len() - u2c_off)).min(READ_CHUNK)]), if upstream_read && u2c.len() - u2c_off < MAX_BUFFER => {
                match result {
                    Ok(0) => { upstream_read = false; if u2c_off == u2c.len() && client_write { let _ = cw.shutdown().await; client_write = false; } },
                    Ok(n) => { if u2c_off == u2c.len() { u2c.clear(); u2c_off = 0; } else if u2c_off > 0 { let remaining = u2c.len() - u2c_off; u2c.copy_within(u2c_off.., 0); u2c.truncate(remaining); u2c_off = 0; } u2c.extend_from_slice(&tmp_u[..n]); last_data = Instant::now(); },
                    Err(_) => break,
                }
            }
            result = uw.write(&c2u[c2u_off..]), if upstream_write && c2u_off < c2u.len() => {
                match result { Ok(0) => break, Ok(n) => { c2u_off += n; up_bytes += n as u64; last_data = Instant::now(); if c2u_off == c2u.len() { c2u.clear(); c2u_off = 0; } }, Err(_) => break }
            }
            result = cw.write(&u2c[u2c_off..]), if client_write && u2c_off < u2c.len() => {
                match result { Ok(0) => break, Ok(n) => { u2c_off += n; down_bytes += n as u64; last_data = Instant::now(); if u2c_off == u2c.len() { u2c.clear(); u2c_off = 0; } }, Err(_) => break }
            }
            _ = sleep_until(next_check) => {
                next_check = Instant::now() + config.revalidate;
                if !policy(&config, id).await.unwrap_or(false) { event = "revoked"; break; }
            }
            _ = sleep(config.idle.min(Duration::from_millis(50))) => {
                if Instant::now().duration_since(last_data) >= config.idle { event = "timeout"; break; }
            }
        }
        if !client_read && c2u_off == c2u.len() && upstream_write { let _ = uw.shutdown().await; upstream_write = false; }
        if !upstream_read && u2c_off == u2c.len() && client_write { let _ = cw.shutdown().await; client_write = false; }
    }
    let _ = audit(&config, id, event, up_bytes, down_bytes).await;
    Ok(())
}

#[tokio::main]
async fn main() -> std::io::Result<()> {
    let mut args = env::args().skip(1);
    let listen: SocketAddr = args.next().expect("listen addr").parse().expect("listen address");
    let upstream: SocketAddr = args.next().expect("upstream addr").parse().expect("upstream address");
    let policy_addr: SocketAddr = args.next().expect("policy addr").parse().expect("policy address");
    let revalidate = Duration::from_millis(args.next().unwrap_or_else(|| "2000".into()).parse().expect("revalidate ms"));
    let idle = Duration::from_millis(args.next().unwrap_or_else(|| "120000".into()).parse().expect("idle ms"));
    let config = Config { upstream, policy: policy_addr, revalidate, idle };
    let socket = Socket::new(
        if listen.is_ipv6() { Domain::IPV6 } else { Domain::IPV4 },
        Type::STREAM,
        Some(Protocol::TCP),
    )?;
    socket.set_reuse_address(true)?;
    socket.set_nonblocking(true)?;
    socket.bind(&listen.into())?;
    socket.listen(64)?;
    let listener: StdTcpListener = socket.into();
    let listener = TcpListener::from_std(listener)?;
    println!("READY");
    let slots = Arc::new(Semaphore::new(256));
    loop {
        let (stream, _) = listener.accept().await?;
        let cfg = config.clone();
        let permit = slots.clone().acquire_owned().await.expect("relay admission semaphore");
        tokio::spawn(async move { let _permit = permit; let _ = relay(stream, cfg).await; });
    }
}

#[cfg(test)]
mod tests {
    use super::{audit_acknowledged, policy_allows};

    #[test]
    fn policy_protocol_accepts_only_exact_allow_receipt() {
        assert!(policy_allows("ALLOW 12\n"));
        assert!(!policy_allows("ALLOW\n"));
        assert!(!policy_allows("ALLOW"));
        assert!(!policy_allows("ALLOWING\n"));
        assert!(!policy_allows("ALLOW nope\n"));
        assert!(!policy_allows("ALLOW 12 extra\n"));
        assert!(!policy_allows("DENY\n"));
        assert!(!policy_allows(""));
    }

    #[test]
    fn audit_protocol_requires_exact_acknowledgement() {
        assert!(audit_acknowledged(b"OK\n"));
        assert!(!audit_acknowledged(b"NO\n"));
        assert!(!audit_acknowledged(b"OK!"));
    }
}
