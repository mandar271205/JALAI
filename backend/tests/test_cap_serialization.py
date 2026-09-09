from xml.etree import ElementTree as ET

from app.integrations.cap.serializer import CAP_NAMESPACE, CAPSerializer


def test_cap_12_xml_serialization_structure():
    alert_payload = {
        "alert_id": "f5c22a7d-test",
        "sender": "jalrakshak-ai@disaster.gov.in",
        "sent_at": "2026-09-08T09:30:00Z",
        "headline": "SEVERE FLASH FLOOD WARNING: Dharavi & Kurla Wards",
        "description": "Rapid water level rise detected. Inundation depth exceeding 0.7m.",
        "instruction": "Avoid low-lying subways. Move to upper floors immediately.",
        "severity": "Extreme",
        "urgency": "Immediate",
        "certainty": "Observed",
        "area_description": "Mumbai Municipal Wards L and G/North",
        "circle": "19.0712,72.8756 2.5",
    }

    xml_output = CAPSerializer.to_xml(alert_payload)
    assert xml_output.startswith("<?xml")

    # Parse and validate standard OASIS CAP 1.2 XML tree
    root = ET.fromstring(xml_output)
    assert root.tag == f"{{{CAP_NAMESPACE}}}alert"

    # Check elements under namespace
    ns = {"cap": CAP_NAMESPACE}
    assert root.find("cap:identifier", ns).text == "f5c22a7d-test"
    assert root.find("cap:status", ns).text == "Actual"
    assert root.find("cap:msgType", ns).text == "Alert"
    assert root.find("cap:scope", ns).text == "Public"

    info = root.find("cap:info", ns)
    assert info is not None
    assert info.find("cap:severity", ns).text == "Extreme"
    assert info.find("cap:urgency", ns).text == "Immediate"
    assert info.find("cap:headline", ns).text == alert_payload["headline"]

    area = info.find("cap:area", ns)
    assert area is not None
    assert area.find("cap:circle", ns).text == "19.0712,72.8756 2.5"
