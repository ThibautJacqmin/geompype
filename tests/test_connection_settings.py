"""Local server settings resolve without COMSOL, network access or output files."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from geompype import Project, _comsol
from geompype._comsol_config import server_settings


class TestConnectionSettings(unittest.TestCase):
    def setUp(self):
        previous = Path.cwd()
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.addCleanup(os.chdir, previous)
        os.chdir(folder.name)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def write_settings(self, settings):
        Path("comsol.local.json").write_text(json.dumps(settings), encoding="utf-8")

    def test_defaults_and_independent_file_fields(self):
        self.assertEqual(server_settings(), ("localhost", 2036))
        self.write_settings({"port": 2040})
        self.assertEqual(server_settings(), ("localhost", 2040))
        self.write_settings({"host": "server.example"})
        self.assertEqual(server_settings(), ("server.example", 2036))

    def test_api_environment_file_precedence_applies_per_field(self):
        self.write_settings({"host": "file.example", "port": 2040})
        os.environ["GEOMPYPE_COMSOL_HOST"] = "env.example"
        self.assertEqual(server_settings(), ("env.example", 2040))
        self.assertEqual(server_settings(host="api.example"), ("api.example", 2040))
        os.environ["GEOMPYPE_COMSOL_PORT"] = "2041"
        self.assertEqual(server_settings(host="api.example"), ("api.example", 2041))
        self.assertEqual(server_settings(port=2042), ("env.example", 2042))
        self.assertEqual(server_settings("api.example", 2043), ("api.example", 2043))

    def test_resolved_arguments_or_environment_do_not_read_local_file(self):
        Path("comsol.local.json").write_text("broken JSON", encoding="utf-8")
        self.assertEqual(server_settings("api.example", 2040), ("api.example", 2040))
        os.environ.update(GEOMPYPE_COMSOL_HOST="env.example", GEOMPYPE_COMSOL_PORT="2041")
        self.assertEqual(server_settings(), ("env.example", 2041))

    def test_unresolved_settings_report_malformed_file_and_unknown_keys(self):
        Path("comsol.local.json").write_text("broken JSON", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "comsol.local.json.*JSON"):
            server_settings()
        for settings in ([], {"hostname": "server.example"}):
            with self.subTest(settings=settings):
                self.write_settings(settings)
                with self.assertRaisesRegex(ValueError, "only the keys"):
                    server_settings()

    def test_invalid_selected_values_are_rejected(self):
        for host in ("", " ", "bad host", 4, None):
            with self.subTest(host=host):
                self.write_settings({"host": host})
                with self.assertRaisesRegex(ValueError, "COMSOL host"):
                    server_settings()
        for port in (0, -1, 65536, True, 2036.5, None, "2036.0", ""):
            with self.subTest(port=port):
                self.write_settings({"port": port})
                with self.assertRaisesRegex(ValueError, "COMSOL port"):
                    server_settings()

    def test_explicit_client_bypasses_file_environment_and_arguments(self):
        Path("comsol.local.json").write_text("broken JSON", encoding="utf-8")
        os.environ["GEOMPYPE_COMSOL_PORT"] = "invalid"
        client = Mock(host="managed.example", port=2040)
        with patch.object(_comsol, "_client", None), \
                patch("geompype.project.get_client", side_effect=AssertionError("Connected")):
            project = Project(client=client, host="", port=-1)
            self.assertEqual((project.host, project.port), ("managed.example", 2040))
            self.assertIs(_comsol.get_client(client=client, host="", port=-1), client)
        client.connect.assert_not_called()

    def test_project_resolves_once_without_connecting_or_creating_outputs(self):
        self.write_settings({"host": "first.example", "port": 2040})
        with patch("geompype.project.get_client", side_effect=AssertionError("Connected")):
            first = Project(output="output/first")
            self.write_settings({"host": "second.example", "port": 2041})
            second = Project(output="output/second")
        self.assertEqual((first.host, first.port), ("first.example", 2040))
        self.assertEqual((second.host, second.port), ("second.example", 2041))
        self.assertFalse(Path("output").exists())
        self.write_settings({"port": 0})
        with patch("geompype.project.get_client", side_effect=AssertionError("Connected")):
            with self.assertRaisesRegex(ValueError, "COMSOL port"):
                Project(output="output/invalid")
        self.assertFalse(Path("output").exists())

    def test_direct_client_uses_settings_without_probe_and_preserves_connection(self):
        self.write_settings({"host": "server.example", "port": 2040})
        client = Mock(host=None, port=None, standalone=False)

        def connect(*, host, port):
            client.host, client.port = host, port

        client.connect.side_effect = connect
        factory = Mock(return_value=client)
        with patch.object(_comsol, "_client", None), \
                patch.dict("sys.modules", {"mph": SimpleNamespace(Client=factory)}), \
                patch("socket.create_connection", side_effect=AssertionError("Disposable probe")):
            self.assertIs(_comsol.get_client(), client)
            self.assertIs(_comsol.get_client(), client)
            factory.assert_called_once_with(host=None)
            client.connect.assert_called_once_with(host="server.example", port=2040)
            self.write_settings({"host": "changed.example", "port": 2040})
            with self.assertRaisesRegex(ValueError, "already connected|connected to"):
                _comsol.get_client()
        client.disconnect.assert_not_called()

