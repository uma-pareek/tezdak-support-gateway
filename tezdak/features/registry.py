"""Feature registry: which features apply to a message and how tools are dispatched.

Changelog
  0.2  dispatch() returns an error dict instead of raising on unknown tools.
  0.1  Static list.
"""

from .address_update import AddressUpdateFeature
from .base import Feature, FeatureContext
from .cancel_order import CancelOrderFeature
from .cod_refund import CodRefundFeature
from .delay_notifier import DelayNotifierFeature
from .handoff import HandoffFeature
from .not_received_helper import NotReceivedHelperFeature
from .promise_tracker import PromiseTrackerFeature
from .rider_feedback import RiderFeedbackFeature
from .slot_picker import SlotPickerFeature
from .wismo_detail import WismoDetailFeature

DISABLED_BY_DEFAULT = ()  # names to leave out of default(); empty today


class FeatureRegistry:
    def __init__(self, features=None):
        self._features: list[Feature] = []
        self._owner: dict[str, Feature] = {}
        for f in features or []:
            self.register(f)

    @classmethod
    def default(cls):
        feats = [WismoDetailFeature(), AddressUpdateFeature(), CancelOrderFeature(), CodRefundFeature(),
                 RiderFeedbackFeature(), SlotPickerFeature(), DelayNotifierFeature(), PromiseTrackerFeature(),
                 HandoffFeature(), NotReceivedHelperFeature()]
        return cls([f for f in feats if f.name not in DISABLED_BY_DEFAULT])

    def register(self, feature: Feature):
        if any(f.name == feature.name for f in self._features):
            raise ValueError("duplicate feature %r" % feature.name)
        for spec in feature.tool_specs():
            if spec["name"] in self._owner:
                raise ValueError("tool %r already registered" % spec["name"])
        self._features.append(feature)
        for spec in feature.tool_specs():
            self._owner[spec["name"]] = feature

    @property
    def features(self):
        return list(self._features)

    def get(self, name):
        return next((f for f in self._features if f.name == name), None)

    def for_context(self, ctx: FeatureContext):
        return [f for f in self._features if f.can_handle(ctx)]

    def all_specs(self):
        return [s for f in self._features for s in f.tool_specs()]

    def specs_for(self, ctx):
        return [s for f in self.for_context(ctx) for s in f.tool_specs()]

    def hints_for(self, ctx):
        hints = [f.prompt_hint(ctx) for f in self.for_context(ctx)]
        return "\n".join(h for h in hints if h)

    def dispatch(self, name, args, ctx):
        owner = self._owner.get(name)
        if owner is None:
            return {"error": "unknown_tool", "name": name}
        try:
            return owner.run_tool(name, args or {}, ctx)
        except Exception as exc:  # a feature bug must not take the chat down
            return {"error": "feature_failed", "feature": owner.name, "detail": "%s: %s" % (type(exc).__name__, exc)}
