"""Topic collection, including publisher/subscriber endpoints and QoS."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import DiagnosticCollector, RosBackend, is_hidden
from ros2_ai_debugger.collectors.nodes import SELF_NODE_NAME
from ros2_ai_debugger.models import PublisherInfo, SubscriberInfo, TopicInfo


def _is_user_endpoint(node_name: str) -> bool:
    """False for the tool's own node and for hidden nodes such as the ros2cli daemon."""
    base = node_name.rsplit("/", 1)[-1]
    return base != SELF_NODE_NAME and not base.startswith("_")


class TopicCollector(DiagnosticCollector):
    name, field = "topics", "topics"

    def __init__(self, backend: RosBackend) -> None:
        self._backend = backend

    def collect(self) -> list[TopicInfo]:
        topics = []
        for name, types in sorted(self._backend.topic_names_and_types()):
            if is_hidden(name):
                continue
            pubs = [
                PublisherInfo(e.node_name, e.topic_type, e.qos)
                for e in self._backend.publishers_info(name)
                if _is_user_endpoint(e.node_name)
            ]
            subs = [
                SubscriberInfo(e.node_name, e.topic_type, e.qos)
                for e in self._backend.subscribers_info(name)
                if _is_user_endpoint(e.node_name)
            ]
            if not pubs and not subs:
                continue  # only our own or hidden-node endpoints (e.g. our /diagnostics subscription)
            topics.append(
                TopicInfo(
                    name=name,
                    types=sorted(types),
                    publishers=sorted(pubs, key=lambda p: p.node_name),
                    subscribers=sorted(subs, key=lambda s: s.node_name),
                )
            )
        return topics
