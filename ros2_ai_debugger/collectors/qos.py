"""QoS compatibility checking.

QoS *data* is collected per endpoint by :class:`TopicCollector`. This module
implements the two request/offer rules from the ROS 2 QoS compatibility
matrix that can be decided from the values rclpy exposes.
"""
from __future__ import annotations

from dataclasses import dataclass

from ros2_ai_debugger.models import PublisherInfo, SubscriberInfo, TopicInfo

_KNOWN_RELIABILITY = {"RELIABLE", "BEST_EFFORT"}
_KNOWN_DURABILITY = {"VOLATILE", "TRANSIENT_LOCAL"}


@dataclass
class QoSMismatch:
    topic: str
    publisher: str
    subscriber: str
    policy: str  # "reliability" | "durability"
    offered: str
    requested: str


def qos_mismatches(topic: TopicInfo) -> list[QoSMismatch]:
    """Return incompatible publisher/subscriber pairs on ``topic``.

    * Reliability: a BEST_EFFORT publisher cannot serve a RELIABLE subscriber.
    * Durability: a VOLATILE publisher cannot serve a TRANSIENT_LOCAL subscriber.

    Endpoints whose policy is not one of the concrete values above (e.g.
    ``SYSTEM_DEFAULT``/``UNKNOWN``) are skipped rather than guessed.
    """
    out: list[QoSMismatch] = []
    for pub in topic.publishers:
        for sub in topic.subscribers:
            out.extend(_pair(topic.name, pub, sub))
    return out


def _pair(topic: str, pub: PublisherInfo, sub: SubscriberInfo) -> list[QoSMismatch]:
    found = []
    p, s = pub.qos, sub.qos
    if (
        p.reliability in _KNOWN_RELIABILITY
        and s.reliability in _KNOWN_RELIABILITY
        and p.reliability == "BEST_EFFORT"
        and s.reliability == "RELIABLE"
    ):
        found.append(QoSMismatch(topic, pub.node_name, sub.node_name, "reliability",
                                 p.reliability, s.reliability))
    if (
        p.durability in _KNOWN_DURABILITY
        and s.durability in _KNOWN_DURABILITY
        and p.durability == "VOLATILE"
        and s.durability == "TRANSIENT_LOCAL"
    ):
        found.append(QoSMismatch(topic, pub.node_name, sub.node_name, "durability",
                                 p.durability, s.durability))
    return found
