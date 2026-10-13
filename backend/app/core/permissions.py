from enum import StrEnum


class Permission(StrEnum):
    TENANT_READ = "tenant:read"
    TENANT_MANAGE_MEMBERS = "tenant:manage_members"
    TENANT_MANAGE_SETTINGS = "tenant:manage_settings"
    DOCUMENT_READ = "document:read"
    DOCUMENT_UPLOAD = "document:upload"
    INVOICE_READ = "invoice:read"
    INVOICE_CORRECT = "invoice:correct"
    APPROVAL_DECIDE = "approval:decide"
    AUDIT_READ = "audit:read"
    ANALYTICS_READ = "analytics:read"


ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "admin": set(Permission),
    "finance": {
        Permission.TENANT_READ,
        Permission.DOCUMENT_READ,
        Permission.DOCUMENT_UPLOAD,
        Permission.INVOICE_READ,
        Permission.INVOICE_CORRECT,
        Permission.ANALYTICS_READ,
    },
    "approver": {
        Permission.TENANT_READ,
        Permission.DOCUMENT_READ,
        Permission.INVOICE_READ,
        Permission.APPROVAL_DECIDE,
        Permission.ANALYTICS_READ,
    },
    "auditor": {
        Permission.TENANT_READ,
        Permission.DOCUMENT_READ,
        Permission.INVOICE_READ,
        Permission.AUDIT_READ,
        Permission.ANALYTICS_READ,
    },
}

SYSTEM_ROLE_NAMES: tuple[str, ...] = ("admin", "finance", "approver", "auditor")


def permissions_for_role(role_name: str) -> set[Permission]:
    return set(ROLE_PERMISSIONS.get(role_name, set()))
