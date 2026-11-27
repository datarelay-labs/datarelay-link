//! Bounded MCP dispatch admission primitive.
//!
//! Python remains responsible for authentication, AI Access, durable jobs,
//! audit and the dispatch itself. This library only tracks an in-process cap.
use std::sync::atomic::{AtomicUsize, Ordering};

#[repr(C)]
pub struct DispatchBudget {
    capacity: usize,
    inflight: AtomicUsize,
}

/// Create a budget. Invalid capacities return null and fail closed at caller.
#[no_mangle]
pub extern "C" fn drlink_mcp_budget_new(capacity: usize) -> *mut DispatchBudget {
    if capacity == 0 {
        return std::ptr::null_mut();
    }
    Box::into_raw(Box::new(DispatchBudget {
        capacity,
        inflight: AtomicUsize::new(0),
    }))
}

/// Atomically take one slot without waiting. Returns 1 if admitted, else 0.
///
/// # Safety
/// `budget` must be null or point to a live value returned by
/// `drlink_mcp_budget_new`; it must not be freed concurrently.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_budget_try_acquire(
    budget: *mut DispatchBudget,
) -> i32 {
    let Some(budget) = budget.as_ref() else { return 0 };
    let mut current = budget.inflight.load(Ordering::Relaxed);
    loop {
        if current >= budget.capacity {
            return 0;
        }
        match budget.inflight.compare_exchange_weak(
            current,
            current + 1,
            Ordering::AcqRel,
            Ordering::Relaxed,
        ) {
            Ok(_) => return 1,
            Err(actual) => current = actual,
        }
    }
}

/// Release one previously acquired slot; extra releases are ignored.
///
/// # Safety
/// `budget` must be null or point to a live value returned by
/// `drlink_mcp_budget_new`; it must not be freed concurrently.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_budget_release(budget: *mut DispatchBudget) {
    let Some(budget) = budget.as_ref() else { return };
    let mut current = budget.inflight.load(Ordering::Relaxed);
    while current > 0 {
        match budget.inflight.compare_exchange_weak(
            current,
            current - 1,
            Ordering::AcqRel,
            Ordering::Relaxed,
        ) {
            Ok(_) => return,
            Err(actual) => current = actual,
        }
    }
}

/// Free a budget after all users have stopped. Concurrent use during free is invalid.
///
/// # Safety
/// `budget` must be null or a live pointer returned by
/// `drlink_mcp_budget_new`, and no thread may use it again after this call.
#[no_mangle]
pub unsafe extern "C" fn drlink_mcp_budget_free(budget: *mut DispatchBudget) {
    if !budget.is_null() {
        drop(Box::from_raw(budget));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn admission_is_bounded_and_release_restores_capacity() {
        let budget = drlink_mcp_budget_new(2);
        unsafe {
            assert_eq!(drlink_mcp_budget_try_acquire(budget), 1);
            assert_eq!(drlink_mcp_budget_try_acquire(budget), 1);
            assert_eq!(drlink_mcp_budget_try_acquire(budget), 0);
            drlink_mcp_budget_release(budget);
            assert_eq!(drlink_mcp_budget_try_acquire(budget), 1);
            drlink_mcp_budget_release(budget);
            drlink_mcp_budget_release(budget);
            drlink_mcp_budget_release(budget);
            assert_eq!(drlink_mcp_budget_try_acquire(budget), 1);
            drlink_mcp_budget_free(budget);
        }
    }

    #[test]
    fn invalid_capacity_fails_closed() {
        assert!(drlink_mcp_budget_new(0).is_null());
    }
}
