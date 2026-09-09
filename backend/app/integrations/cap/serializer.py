from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree as ET

CAP_NAMESPACE = "urn:oasis:names:tc:emergency:cap:1.2"


class CAPSerializer:
    """
    OASIS Common Alerting Protocol (CAP) v1.2 Serializer.
    Pure standards-compliant XML serialization.
    """

    @staticmethod
    def to_xml(alert_dict: dict[str, Any]) -> str:
        # Root <alert> element with OASIS CAP 1.2 namespace
        alert = ET.Element("alert", xmlns=CAP_NAMESPACE)

        identifier = ET.SubElement(alert, "identifier")
        identifier.text = str(alert_dict.get("alert_id", "alert-001"))

        sender = ET.SubElement(alert, "sender")
        sender.text = alert_dict.get("sender", "jalrakshak-backend@gov.in")

        sent = ET.SubElement(alert, "sent")
        sent.text = alert_dict.get("sent_at", datetime.now(UTC).isoformat())

        status = ET.SubElement(alert, "status")
        status.text = alert_dict.get("cap_status", "Actual")

        msg_type = ET.SubElement(alert, "msgType")
        msg_type.text = alert_dict.get("msg_type", "Alert")

        scope = ET.SubElement(alert, "scope")
        scope.text = alert_dict.get("scope", "Public")

        # <info> container
        info = ET.SubElement(alert, "info")

        category = ET.SubElement(info, "category")
        category.text = alert_dict.get("category", "Met")

        event = ET.SubElement(info, "event")
        event.text = alert_dict.get("event", "Flood Warning")

        urgency = ET.SubElement(info, "urgency")
        urgency.text = alert_dict.get("urgency", "Immediate")

        severity = ET.SubElement(info, "severity")
        severity.text = alert_dict.get("severity", "Extreme")

        certainty = ET.SubElement(info, "certainty")
        certainty.text = alert_dict.get("certainty", "Observed")

        headline = ET.SubElement(info, "headline")
        headline.text = alert_dict.get("headline", "")

        description = ET.SubElement(info, "description")
        description.text = alert_dict.get("description", "")

        instruction = ET.SubElement(info, "instruction")
        instruction.text = alert_dict.get("instruction", "")

        area = ET.SubElement(info, "area")
        area_desc = ET.SubElement(area, "areaDesc")
        area_desc.text = alert_dict.get("area_description", "Monitored Municipal Ward")

        if alert_dict.get("circle"):
            circle = ET.SubElement(area, "circle")
            circle.text = alert_dict.get("circle")  # lat,lon radius

        if alert_dict.get("polygon"):
            polygon = ET.SubElement(area, "polygon")
            polygon.text = alert_dict.get("polygon")

        xml_str = ET.tostring(alert, encoding="utf-8", xml_declaration=True).decode("utf-8")
        return xml_str
