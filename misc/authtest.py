from dataclasses import dataclass
from typing import Callable

type PermissionType = str


@dataclass(frozen=True)
class User:
    name: str
    password_hash: str
    permissions: set[PermissionType]


@dataclass(frozen=True)
class Group:
    name: str
    members: set[User]
    permissions: set[PermissionType]


@dataclass(frozen=True)
class Rule:
    name: str
    code: str

    def evaluate(self, context) -> bool:
        return bool(exec(self.code, context))


@dataclass(frozen=True)
class Action:
    name: str
    fn: Callable
    rules: set[Rule]


@dataclass(frozen=True)
class Resource:
    actions: dict[str, Action]

    def authorize(self, user: User, action: str) -> bool: ...


def test_authorization():
    u1 = User("john", "abc", {"user.me"})
    g1 = Group("g", {u1}, {"user.list"})

    users = [u1]
    groups = [g1]

    def action_user_me(user_name: str) -> dict:
        print(f"User is {user_name}")
        return {"username": user_name}

    def action_user_list() -> list[dict]:
        print("User list")
        return [{"uid": i} for i in range(1, 11)]

    def action_user_delete() -> None:
        print("User delete")

    a1 = Action("user.me", action_user_me, set())
    a2 = Action("user.list", action_user_list, set())
    a3 = Action(
        "user.delete",
        action_user_delete,
        {Rule("John can delete", 'user.name == "john"')},
    )

    user_resource = Resource(actions={a1.name: a1, a2.name: a2, a3.name: a3})
    assert user_resource.authorize(u1, "user.me") == True
    assert user_resource.authorize(u1, "user.list") == True
    assert user_resource.authorize(u1, "user.delete") == True
