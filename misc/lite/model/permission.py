from dataclasses import dataclass


@dataclass
class Role:
    id: str
    name: str


@dataclass
class RolePermission:
    id: str
    role_id: str
    permission_id: str


@dataclass
class Permission:
    id: str
    resource: str
    action: str

