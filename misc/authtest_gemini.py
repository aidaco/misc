from dataclasses import dataclass
from typing import Callable, Any

PermissionType = str


@dataclass(frozen=True)
class User:
    name: str
    password_hash: str
    permissions: set[PermissionType]
    groups: set[str]  # Add group membership to User


@dataclass(frozen=True)
class Group:
    name: str
    permissions: set[PermissionType]


@dataclass(frozen=True)
class Rule:
    name: str
    code: str

    def evaluate(self, context: dict[str, Any]) -> bool:
        """
        Evaluates the rule code within the given context.
        WARNING: Using eval is insecure and should be replaced
                 in a production environment with a safer method.
                 This is used here for simplicity as per instructions.
        """
        try:
            # WARNING: Security risk - use eval with caution!
            return bool(eval(self.code, {}, context))
        except Exception as e:
            print(
                f"Error evaluating rule '{self.name}': {e}"
            )  # Basic error handling for rules
            return False  # Rule evaluation fails safe


@dataclass(frozen=True)
class Action:
    name: str
    fn: Callable
    rules: set[Rule]


@dataclass(frozen=True)
class Resource:
    actions: dict[str, Action]

    def authorize(
        self, user: User, action_name: str, context_data: dict[str, Any] | None = None
    ) -> bool:
        """
        Authorizes a user to perform an action on the resource based on a hybrid RBAC/ABAC approach.
        """
        group_permission_granted = False
        for group_name in user.groups:
            # In a real system, you'd likely have a Group registry to look up Group objects by name
            # For this example, we'll assume group permissions are checked directly against action_name
            if action_name in get_group_permissions(
                group_name
            ):  # Assuming a function to get group permissions
                group_permission_granted = True
                break  # Granted if any group allows it

        action = self.actions.get(action_name)
        if not action:
            return False  # Action not defined for this resource, deny

        # ABAC rule evaluation (only if RBAC allows or we want rules to be independent - in this case, dependent on RBAC)
        if (
            group_permission_granted or not get_group_permissions(any)
        ):  # if group permission is granted, or if group permissions are not applicable at all
            all_rules_pass = True
            for rule in action.rules:
                context = {
                    "user": user,
                    "groups": get_user_groups_objects(
                        user
                    ),  # Assuming function to get Group objects for user
                    "resource": self,
                    "action_name": action_name,
                    "context_data": context_data or {},
                }
                if not rule.evaluate(context):
                    all_rules_pass = False
                    break  # At least one rule failed, authorization denied by ABAC
            return group_permission_granted and all_rules_pass  # Hybrid: RBAC AND ABAC
        else:
            return False  # RBAC denied, ABAC not even checked


# --- Mock functions for group permissions and user groups (replace with actual logic) ---
group_permissions_map = {
    "admin": {"user.list", "user.delete", "user.me", "group.create"},
    "editor": {"user.me", "user.list"},
    "viewer": {"user.me", "user.list"},
    "marketing": {"resource.promote"},
}


def get_group_permissions(group_name: str) -> set[PermissionType]:
    return group_permissions_map.get(
        group_name, set()
    )  # Return empty set if group not found


group_registry = {  # Mock group registry for testing purposes
    "admin": Group("admin", group_permissions_map["admin"]),
    "editor": Group("editor", group_permissions_map["editor"]),
    "viewer": Group("viewer", group_permissions_map["viewer"]),
    "marketing": Group("marketing", group_permissions_map["marketing"]),
}


def get_user_groups_objects(user: User) -> list[Group]:
    return [
        group for group_name in user.groups if (group := group_registry.get(group_name))
    ]


def test_authorization():
    u1 = User("john", "abc", {"user.me"}, {"editor"})  # John is in 'editor' group
    u2 = User(
        "jane", "xyz", {"user.me"}, {"viewer", "marketing"}
    )  # Jane is in 'viewer' and 'marketing' groups
    u3 = User("peter", "123", {"user.me"}, {})  # Peter is in no groups
    u_admin = User(
        "admin_user", "pwd", {"*"}, {"admin"}
    )  # Admin user, member of 'admin' group

    def action_user_me(
        user: User,
    ) -> dict:  # Context aware action, now takes user object
        print(f"User is {user.name}")
        return {"username": user.name}

    def action_user_list() -> list[dict]:
        print("User list")
        return [{"uid": i} for i in range(1, 11)]

    def action_user_delete(
        user: User, target_user_id: int
    ) -> None:  # Context aware action, takes target_user_id and user
        print(f"User {user.name} deleting user {target_user_id}")

    def action_resource_promote(
        resource_id: int, campaign_name: str, user: User
    ) -> None:  # Example action with more context
        print(
            f"User {user.name} promoting resource {resource_id} in campaign {campaign_name}"
        )

    a1 = Action("user.me", action_user_me, set())
    a2 = Action("user.list", action_user_list, set())
    a3 = Action(
        "user.delete",
        action_user_delete,
        {
            Rule(
                "Admin can delete",
                'context_data.target_user_id != user.name and "admin" in user.groups',
            )
        },  # Rule now checks for admin group and context data
    )
    a4 = Action(
        "resource.promote",
        action_resource_promote,
        {
            Rule(
                "Marketing group can promote",
                '"marketing" in user.groups and context_data.campaign_name != "sensitive_campaign"',
            )
        },  # Rule checking group and context data
    )

    user_resource = Resource(
        actions={a1.name: a1, a2.name: a2, a3.name: a3, a4.name: a4}
    )

    # --- Test Cases ---
    print("--- Test Case 1: John (editor) - user.me ---")
    assert (
        user_resource.authorize(u1, "user.me") == True
    ), "Test Case 1 Failed: John (editor) should access user.me"

    print("--- Test Case 2: John (editor) - user.list ---")
    assert (
        user_resource.authorize(u1, "user.list") == True
    ), "Test Case 2 Failed: John (editor) should access user.list"

    print(
        "--- Test Case 3: John (editor) - user.delete (without admin role, rule should deny) ---"
    )
    assert (
        user_resource.authorize(u1, "user.delete", {"target_user_id": 123}) == False
    ), "Test Case 3 Failed: John (editor) should NOT delete without admin & rule"

    print(
        "--- Test Case 4: Admin user - user.delete (with admin role, rule should allow) ---"
    )
    assert (
        user_resource.authorize(u_admin, "user.delete", {"target_user_id": 456}) == True
    ), "Test Case 4 Failed: Admin user should delete"

    print(
        "--- Test Case 5: Peter (no group) - user.list (no group permission, should be denied by RBAC) ---"
    )
    assert (
        user_resource.authorize(u3, "user.list") == False
    ), "Test Case 5 Failed: Peter (no group) should NOT access user.list"

    print(
        "--- Test Case 6: Jane (viewer, marketing) - resource.promote (marketing group, campaign allowed) ---"
    )
    assert (
        user_resource.authorize(
            u2, "resource.promote", {"resource_id": 100, "campaign_name": "summer_sale"}
        )
        == True
    ), "Test Case 6 Failed: Jane (marketing) should promote in allowed campaign"

    print(
        "--- Test Case 7: Jane (viewer, marketing) - resource.promote (marketing group, sensitive campaign denied by rule) ---"
    )
    assert (
        user_resource.authorize(
            u2,
            "resource.promote",
            {"resource_id": 200, "campaign_name": "sensitive_campaign"},
        )
        == False
    ), "Test Case 7 Failed: Jane (marketing) should NOT promote in sensitive campaign"

    print(
        "--- Test Case 8: John (editor) - resource.promote (no marketing group, denied by RBAC) ---"
    )
    assert (
        user_resource.authorize(
            u1, "resource.promote", {"resource_id": 300, "campaign_name": "fall_promo"}
        )
        == False
    ), "Test Case 8 Failed: John (editor) should NOT promote (no marketing group)"

    print("--- Test Case 9: Admin user - user.list (admin group allows) ---")
    assert (
        user_resource.authorize(u_admin, "user.list") == True
    ), "Test Case 9 Failed: Admin user should access user.list"

    print(
        "--- Test Case 10: Admin user - group.create (admin group allows - testing different action) ---"
    )
    assert (
        user_resource.authorize(u_admin, "group.create") == True
    ), "Test Case 10 Failed: Admin user should access group.create"

    print(
        "--- Test Case 11: John (editor) - group.create (editor group does not allow) ---"
    )
    assert (
        user_resource.authorize(u1, "group.create") == False
    ), "Test Case 11 Failed: Editor should not access group.create"


if __name__ == "__main__":
    test_authorization()
    print("\nAll tests completed.")
