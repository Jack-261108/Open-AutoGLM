"""Offline tests for accessibility dumps and their device commands."""

from types import SimpleNamespace

from phone_agent.accessibility import (
    format_ui_tree,
    parse_android_hierarchy,
    parse_harmony_hierarchy,
    parse_ios_source,
)
from phone_agent.adb.device import get_ui_tree as get_adb_ui_tree
from phone_agent.hdc.device import get_ui_tree as get_hdc_ui_tree


ANDROID_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node text="" content-desc="" class="android.widget.FrameLayout"
        clickable="false" bounds="[0,0][200,400]">
    <node text="设置" content-desc="" class="android.widget.TextView"
          clickable="true" enabled="true" scrollable="false"
          bounds="[0,0][200,80]" />
    <node text="secret" content-desc="password" class="android.widget.EditText"
          password="true" clickable="true" enabled="true"
          bounds="[0,100][200,180]" />
    <node text="" content-desc="" class="android.widget.View"
          clickable="false" bounds="[0,200][20,220]" />
  </node>
</hierarchy>
"""

HARMONY_JSON = """
DumpLayout saved to:/data/local/tmp/layout.json
{
  "attributes": {
    "type": "root",
    "text": "",
    "bounds": "[0,0][100,100]",
    "clickable": "false",
    "visible": "true"
  },
  "children": [
    {
      "attributes": {
        "type": "Button",
        "text": "确定",
        "bounds": "[10,10][90,40]",
        "clickable": "true",
        "enabled": "true",
        "visible": "true"
      },
      "children": []
    },
    {
      "attributes": {
        "type": "Text",
        "text": "hidden",
        "bounds": "[0,50][10,60]",
        "clickable": "true",
        "visible": "false"
      },
      "children": []
    }
  ]
}
"""

IOS_JSON = {
    "value": {
        "type": "XCUIElementTypeApplication",
        "name": "Settings",
        "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
        "children": [
            {
                "type": "XCUIElementTypeButton",
                "name": "WLAN",
                "label": "WLAN",
                "enabled": True,
                "visible": True,
                "rect": {"x": 20, "y": 100, "width": 100, "height": 40},
                "children": [],
            },
            {
                "type": "XCUIElementTypeButton",
                "name": "Offscreen",
                "visible": False,
                "rect": {"x": 0, "y": 0, "width": 10, "height": 10},
                "children": [
                    {
                        "type": "XCUIElementTypeStaticText",
                        "name": "Hidden child",
                        "visible": True,
                        "rect": {"x": 0, "y": 0, "width": 10, "height": 10},
                    }
                ],
            },
        ],
    }
}

IOS_XML = """
<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="Settings"
    x="0" y="0" width="390" height="844" enabled="true" visible="true">
  <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="通用"
      x="10" y="20" width="40" height="20" enabled="true" visible="true" />
</XCUIElementTypeApplication>
"""


def test_android_hierarchy_keeps_tappable_labels_and_hides_passwords():
    tree = parse_android_hierarchy(ANDROID_XML)

    assert tree is not None
    assert tree.width == 200
    assert tree.height == 400
    labels = {element.text: element for element in tree.elements}
    assert labels["设置"].clickable is True
    assert labels["设置"].role == "TextView"
    assert labels["password"].text == "password"
    assert "secret" not in labels
    assert "" not in labels
    rendered = format_ui_tree(tree)
    assert 'TextView "设置" clickable center=[500,100]' in rendered


def test_harmony_hierarchy_skips_invisible_nodes():
    tree = parse_harmony_hierarchy(HARMONY_JSON)

    assert tree is not None
    assert [element.text for element in tree.elements] == ["确定"]
    assert tree.elements[0].clickable is True
    assert "hidden" not in format_ui_tree(tree)


def test_ios_json_and_xml_sources_use_element_frame():
    parsed = parse_ios_source(IOS_JSON)
    assert parsed is not None
    assert parsed.width == 390
    assert parsed.height == 844
    assert [element.text for element in parsed.elements] == ["Settings", "WLAN"]
    assert parsed.elements[1].role == "Button"
    assert parsed.elements[1].clickable is True
    assert "Hidden child" not in format_ui_tree(parsed)

    xml_tree = parse_ios_source(IOS_XML)
    assert xml_tree is not None
    assert xml_tree.elements[0].text == "Settings"
    assert any(element.text == "通用" for element in xml_tree.elements)


ANDROID_SCROLL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node text="" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">
    <node text="" class="android.widget.ScrollView" scrollable="true"
          bounds="[0,0][1080,5000]">
      <node text="设置" class="android.widget.TextView" clickable="true" enabled="true"
            bounds="[0,100][200,180]" />
      <node text="更下面" class="android.widget.TextView" clickable="true" enabled="true"
            bounds="[0,3000][200,3100]" />
    </node>
  </node>
</hierarchy>
"""


def test_screen_frame_ignores_bounds_outside_the_root():
    android = parse_android_hierarchy(ANDROID_SCROLL_XML)
    assert android is not None
    assert (android.width, android.height) == (1080, 2400)
    rendered = format_ui_tree(android)
    assert 'TextView "设置" clickable center=[92,58]' in rendered
    assert "更下面" not in rendered

    harmony = parse_harmony_hierarchy(
        """
        {
          "attributes": {"type": "root", "bounds": "[0,0][100,200]", "visible": "true"},
          "children": [
            {
              "attributes": {
                "type": "Button", "text": "确定", "bounds": "[10,10][90,40]",
                "clickable": "true", "enabled": "true", "visible": "true"
              }
            },
            {
              "attributes": {
                "type": "Text", "text": "远处", "bounds": "[0,400][40,480]",
                "clickable": "true", "visible": "true"
              }
            }
          ]
        }
        """
    )
    assert harmony is not None
    assert (harmony.width, harmony.height) == (100, 200)
    assert 'Button "确定" clickable center=[500,125]' in format_ui_tree(harmony)
    assert "远处" not in format_ui_tree(harmony)

    ios = parse_ios_source(
        {
            "value": {
                "type": "XCUIElementTypeApplication",
                "name": "Settings",
                "rect": {"x": 0, "y": 0, "width": 390, "height": 844},
                "children": [
                    {
                        "type": "XCUIElementTypeButton",
                        "name": "settings_button",
                        "label": "设置",
                        "enabled": True,
                        "visible": True,
                        "rect": {"x": 0, "y": 100, "width": 100, "height": 40},
                    },
                    {
                        "type": "XCUIElementTypeButton",
                        "name": "below_button",
                        "label": "更下面",
                        "visible": True,
                        "rect": {"x": 0, "y": 2000, "width": 80, "height": 20},
                    },
                ],
            }
        }
    )
    assert ios is not None
    assert (ios.width, ios.height) == (390, 844)
    ios_text = format_ui_tree(ios)
    assert 'Button "设置" clickable center=[128,142]' in ios_text
    assert "settings_button" not in ios_text
    assert "更下面" not in ios_text

    ios_xml = parse_ios_source(
        """
        <XCUIElementTypeApplication name="Settings" x="0" y="0" width="390" height="844"
            enabled="true" visible="true">
          <XCUIElementTypeButton name="settings_button" label="设置"
              x="0" y="100" width="100" height="40" enabled="true" visible="true" />
        </XCUIElementTypeApplication>
        """
    )
    assert ios_xml is not None
    assert 'Button "设置"' in format_ui_tree(ios_xml)
    assert "settings_button" not in format_ui_tree(ios_xml)


def test_adb_dump_command_reads_xml(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "exec-out" in cmd:
            return SimpleNamespace(returncode=0, stdout=ANDROID_XML.encode(), stderr=b"")
        return SimpleNamespace(
            returncode=0,
            stdout="UI hierchary dumped to: /sdcard/window_dump.xml",
            stderr="",
        )

    monkeypatch.setattr("phone_agent.adb.device.subprocess.run", fake_run)

    tree = get_adb_ui_tree("serial-1")

    assert tree is not None
    assert calls[0] == [
        "adb",
        "-s",
        "serial-1",
        "shell",
        "uiautomator",
        "dump",
        "--compressed",
        "/sdcard/window_dump.xml",
    ]
    assert calls[1][:3] == ["adb", "-s", "serial-1"]


def test_adb_failed_dump_does_not_read_stale_file(monkeypatch):
    failures = (
        SimpleNamespace(returncode=1, stdout="ERROR: could not get idle state.", stderr=""),
        SimpleNamespace(returncode=0, stdout="ERROR: could not get idle state.", stderr=""),
    )
    for failure in failures:
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if "exec-out" in cmd:
                return SimpleNamespace(returncode=0, stdout=ANDROID_XML.encode(), stderr=b"")
            return failure

        monkeypatch.setattr("phone_agent.adb.device.subprocess.run", fake_run)

        assert get_adb_ui_tree("serial-1") is None
        assert all("exec-out" not in cmd for cmd in calls)


def test_hdc_dump_command_cats_saved_json(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "cat" in cmd:
            return SimpleNamespace(
                returncode=0,
                stdout=HARMONY_JSON,
                stderr="",
            )
        return SimpleNamespace(
            returncode=0,
            stdout="DumpLayout saved to:/data/local/tmp/layout.json\n",
            stderr="",
        )

    monkeypatch.setattr("phone_agent.hdc.connection.subprocess.run", fake_run)

    tree = get_hdc_ui_tree("hdc-1")

    assert tree is not None
    assert tree.elements[0].text == "确定"
    assert calls[0][:4] == ["hdc", "-t", "hdc-1", "shell"]
    assert "uitest" in calls[0] and "dumpLayout" in calls[0]
    assert calls[1][-2:] == ["cat", "/data/local/tmp/layout.json"]


def test_hdc_failed_dump_does_not_read_saved_json(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "cat" in cmd:
            return SimpleNamespace(returncode=0, stdout=HARMONY_JSON, stderr="")
        return SimpleNamespace(
            returncode=1,
            stdout="ERROR: dump failed /data/local/tmp/layout.json\n",
            stderr="",
        )

    monkeypatch.setattr("phone_agent.hdc.connection.subprocess.run", fake_run)

    assert get_hdc_ui_tree("hdc-1") is None
    assert len(calls) == 1


def test_ios_ui_tree_failure_does_not_print(monkeypatch, capsys):
    def fail_get(*args, **kwargs):
        raise RuntimeError("wda down")

    monkeypatch.setattr("requests.get", fail_get)
    from phone_agent.xctest.device import get_ui_tree

    assert get_ui_tree("http://wda.invalid", session_id="sess") is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_ios_factory_reads_wda_source(monkeypatch):
    from phone_agent.device_factory import DeviceFactory, DeviceType

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return IOS_JSON

    def fake_get(url, params=None, timeout=None, verify=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr("requests.get", fake_get)
    factory = DeviceFactory(
        DeviceType.IOS, wda_url="http://wda.local:8100", session_id="sess"
    )

    tree = factory.get_ui_tree()

    assert tree is not None
    assert captured["url"] == "http://wda.local:8100/session/sess/source"
    assert captured["params"] == {"format": "json"}
    assert any(element.text == "WLAN" for element in tree.elements)
