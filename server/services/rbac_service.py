from enum import Enum
from typing import List

class Permission(str, Enum):
    """All permissions in the system."""
    # Ticket permissions
    TICKET_CREATE = "ticket:create"
    TICKET_VIEW = "ticket:view"
    TICKET_ASSIGN = "ticket:assign"
    TICKET_CHANGE_STATUS = "ticket:change_status"
    TICKET_CHANGE_LEVEL = "ticket:change_level"
    
    # RCA permissions
    RCA_CREATE = "rca:create"
    RCA_EDIT = "rca:edit"
    RCA_SUBMIT = "rca:submit"
    RCA_APPROVE = "rca:approve"
    
    # Attachment permissions
    ATTACHMENT_UPLOAD = "attachment:upload"
    ATTACHMENT_DEPRECATE = "attachment:deprecate"
    
    # Admin permissions
    ANALYTICS_VIEW = "analytics:view"
    USERS_MANAGE = "users:manage"

class RBACService:
    """Role-based access control."""
    
    # Permission matrix: role -> list of permissions
    ROLE_PERMISSIONS = {
        "platform_admin": [
            Permission.TICKET_CREATE,
            Permission.TICKET_VIEW,
            Permission.TICKET_ASSIGN,
            Permission.TICKET_CHANGE_STATUS,
            Permission.TICKET_CHANGE_LEVEL,
            Permission.RCA_CREATE,
            Permission.RCA_EDIT,
            Permission.RCA_SUBMIT,
            Permission.RCA_APPROVE,
            Permission.ATTACHMENT_UPLOAD,
            Permission.ATTACHMENT_DEPRECATE,
            Permission.ANALYTICS_VIEW,
            Permission.USERS_MANAGE,
        ],
        "company_admin": [
            Permission.TICKET_CREATE,
            Permission.TICKET_VIEW,
            Permission.TICKET_ASSIGN,
            Permission.TICKET_CHANGE_STATUS,
            Permission.TICKET_CHANGE_LEVEL,
            Permission.RCA_CREATE,
            Permission.RCA_EDIT,
            Permission.RCA_SUBMIT,
            Permission.RCA_APPROVE,
            Permission.ATTACHMENT_UPLOAD,
            Permission.ATTACHMENT_DEPRECATE,
            Permission.ANALYTICS_VIEW,
            Permission.USERS_MANAGE,
        ],
        "engineer": [
            Permission.TICKET_CREATE,
            Permission.TICKET_VIEW,
            Permission.TICKET_CHANGE_STATUS,
            Permission.RCA_CREATE,
            Permission.RCA_EDIT,
            Permission.RCA_SUBMIT,
            Permission.ATTACHMENT_UPLOAD,
        ],
        "requester": [
            Permission.TICKET_CREATE,
            Permission.TICKET_VIEW,
            Permission.ATTACHMENT_UPLOAD,
        ],
    }
    
    @staticmethod
    def has_permission(role: str, permission: Permission) -> bool:
        """Check if role has permission."""
        permissions = RBACService.ROLE_PERMISSIONS.get(role, [])
        return permission in permissions
    
    @staticmethod
    def get_permissions(role: str) -> List[Permission]:
        """Get all permissions for a role."""
        return RBACService.ROLE_PERMISSIONS.get(role, [])
    
    @staticmethod
    def require_permission(role: str, permission: Permission) -> bool:
        """Enforce permission (raises exception if not allowed)."""
        if not RBACService.has_permission(role, permission):
            from utils.errors import ForbiddenError
            raise ForbiddenError(f"Missing permission: {permission}")
        return True