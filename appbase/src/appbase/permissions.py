from dataclasses import dataclass
from typing import Literal, Protocol, Any

PERMIT = True
DENY = False
PASS = None
type Decision = bool | None


class AuthorizerType(Protocol):
    def __call__(self, subject: Any, resource: Any, action: Any) -> Decision: ...


@dataclass
class Rules:
    rules: set[AuthorizerType]

    def add(self, rule: AuthorizerType) -> AuthorizerType:
        self.rules.add(rule)
        return rule

    def remove(self, rule: AuthorizerType) -> AuthorizerType:
        self.rules.remove(rule)
        return rule

    def authorize(self, subject: Any, resource: Any, action: Any) -> bool | None:
        try:
            return all(rule(subject, resource, action) for rule in self.rules)
        except Exception:
            return False


class HasId(Protocol):
    id: int


class HasOwner(Protocol):
    owner_id: int


class HasPermissions(Protocol):
    permissions: set[str]


class HasRole(Protocol):
    role: str


def permit_admins(subject: HasRole, resource: Any, action: Any) -> Decision:
    return subject.role == "admin" or None


def permit_owner(subject: HasId, resource: HasOwner, action: Any) -> Decision:
    return subject.id == resource.owner_id or None


def default_permit(subject: Any, resource: Any, action: Any) -> Decision:
    return PERMIT


def default_deny(subject: Any, resource: Any, action: Any) -> Decision:
    return DENY
