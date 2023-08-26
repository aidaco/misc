class AuthorizationRequest(typing.NamedTuple):
    """Request to authorize an agent, resource, and action."""

    agent: typing.Any
    resource: typing.Any
    action: typing.Any


class AuthorizationPolicy(typing.Protocol):
    """A specific rule for permitting or denying access."""

    def check(self, request: AuthorizationRequest) -> bool:
        """Boolean check if the policy holds."""


class PolicyInformationPoint(typing.Protocol):
    """Access external information sources."""


class PolicyDecisionPoint(typing.Protocol):
    """Makes decisions for Authorization Requests using configured policies."""

    def add_pip(self, pip: PolifyInformationPoint):
        """Add a new external information source."""

    def add_permitting(self, policy: AuthorizationPolicy):
        """Add a policy that permits access."""

    def add_denying(self, policy: AuthorizationPolicy):
        """Add a policy that denies access."""

    def decide(self, request: AuthorizationRequest) -> bool:
        """Permit or Deny the incoming request."""


class PolicyEnforcementPoint(typing.Protocol):
    """Creates, dispatches, and resolves Authorization Requests."""

    def enforce(self, *args, **kwargs) -> bool:
        """Enforce set policies on an incoming request."""
