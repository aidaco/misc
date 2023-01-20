import pytest

import misc.abac


def test_core_system():
    pip = misc.abac.PolicyInformationPoint()
    pdp = misc.abac.PolicyDecisionPoint(pip)
    pep = misc.abac.PolicyEnforcementPoint(pdp)


def test_dataclass_models():
    @dataclass
    class Environment:
        user_freeze: bool
        post_freeze: bool

    @dataclass
    class User:
        id: int
        role: str

    @dataclass
    class Post:
        id: int
        author: User

    auth = misc.abac.Auth(User, Post, Environment(False, False))

    @auth.granting
    def roles_with_full_access(user: auth.Agent[User]) -> bool:
        if user.role in {"system", "owner"}:
            return True
        return False

    @auth.denying
    def users_cant_modify_if_posts_frozen(
        env: auth.Environment[Environment], action: auth.Action[Post]
    ):
        if env.post_freeze and action in {"create", "update", "delete"}:
            return False
        return True

    @auth.granting
    def users_have_self_access(user: auth.Agent[User], target: auth.Target[User]):
        if user.id == target.id:
            return True
        return False

    @auth.granting
    def users_have_full_access_to_own_posts(
        user: auth.Agent[User], post: auth.Target[Post]
    ) -> bool:
        if user.id == post.author.id:
            return True
        return False

    @auth.denying
    def deny_access_by_default() -> bool:
        return False

    @auth.create
    def create_user(*args) -> User:
        print(f"Create user: {args}")

    @auth.create
    def create_user(*args) -> User:
        print(f"Create user: {args}")
