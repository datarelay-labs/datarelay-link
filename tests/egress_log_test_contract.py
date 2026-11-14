"""Connection audit file permissions: root-only or least-privilege egress service access."""
import grp
import stat
import subprocess


def assert_private_log(case, path):
    st = path.stat()
    mode = stat.S_IMODE(st.st_mode)
    case.assertEqual(mode & 0o007, 0, f"{path.name} must not grant world access")
    if mode == 0o600:
        return
    # Production's named-user ACL exposes an effective rw mask as 0660.
    # Without ACL support, root:drlink-egress 0660 is the documented fallback.
    case.assertEqual(mode, 0o660, f"{path.name} has unexpected permissions")
    case.assertEqual(st.st_uid, 0, f"{path.name} must remain root-owned")
    try:
        acl = subprocess.check_output(
            ["getfacl", "-cp", str(path)], text=True, stderr=subprocess.DEVNULL
        ).splitlines()
    except (OSError, subprocess.CalledProcessError):
        acl = []
    if "user:drlink-egress:rw-" in acl:
        case.assertIn("group::---", acl, "ACL group owner must not gain access")
        case.assertIn("other::---", acl, "ACL must deny all other users")
        return
    case.assertEqual(
        st.st_gid,
        grp.getgrnam("drlink-egress").gr_gid,
        "0660 without a named-user ACL must target only drlink-egress group",
    )
