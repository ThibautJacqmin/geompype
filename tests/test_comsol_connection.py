"""Connection ownership: reuse one client without probes or automatic shutdown."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from geompype import _comsol


class TestComsolConnection(unittest.TestCase):
    def test_server_tests_refuse_a_process_that_would_exit_after_testing(self):
        import comsol_support

        with patch.object(comsol_support, "_client", None), \
                patch.object(comsol_support, "sys", SimpleNamespace(flags=SimpleNamespace(interactive=0))), \
                patch.object(comsol_support, "project_client") as connect:
            with self.assertRaisesRegex(RuntimeError, "python -i"):
                comsol_support.get_client()
            connect.assert_not_called()

    def test_connect_reuses_the_client_and_never_disconnects_it(self):
        client = Mock(host=None, port=None, standalone=False)

        def connect(*, port, host):
            client.host, client.port = host, port

        client.connect.side_effect = connect
        factory = Mock(return_value=client)
        with patch.object(_comsol, "_client", None), \
                patch.dict("sys.modules", {"mph": SimpleNamespace(Client=factory)}), \
                patch("socket.create_connection", side_effect=AssertionError("Disposable TCP probe")):
            self.assertIs(_comsol.get_client(host="localhost", port=2036), client)
            self.assertIs(_comsol.get_client(host="localhost", port=2036), client)
            factory.assert_called_once_with(host=None)
            client.connect.assert_called_once_with(port=2036, host="localhost")
            with self.assertRaises(ValueError):
                _comsol.get_client(host="localhost", port=2037)
            client.disconnect.assert_not_called()
