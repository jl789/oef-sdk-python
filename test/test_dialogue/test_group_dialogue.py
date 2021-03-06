# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2018 Fetch.AI Limited
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------


"""
This module contains tests on the usage of :class:`~oef.dialogue.GroupDialogues`.
"""
import asyncio
import random

from oef.proxy import OEFNetworkProxy, OEFLocalProxy
from oef.query import Query, Eq, Constraint
from oef.schema import Description, DataModel, AttributeSchema
from test.conftest import NetworkOEFNode, _ASYNCIO_DELAY
from test.test_dialogue.dialogue_agents import ClientAgentGroupDialogueTest, ServerAgentTest


class TestGroupDialogues:

    def test_group_dialogue_one_client_n_servers_network(self, oef_addr, oef_port):
        with NetworkOEFNode():
            client_proxy = OEFNetworkProxy("client", oef_addr=oef_addr, port=oef_port)
            client = ClientAgentGroupDialogueTest(client_proxy)
            client.connect()

            N = 10
            server_proxies = [OEFNetworkProxy("server_{:02d}".format(i),
                                               oef_addr=oef_addr, port=oef_port) for i in range(N)]
            server_data_model = DataModel("server", [AttributeSchema("foo", bool, True)])

            servers = [ServerAgentTest(server_proxy, price=random.randint(10, 100)) for server_proxy in server_proxies]
            for server in servers:
                server.connect()
                server.register_service(0, Description({"foo": True}, server_data_model))

            best_server = ServerAgentTest(OEFNetworkProxy("best_server", oef_addr=oef_addr, port=oef_port), price=5)
            best_server.connect()
            best_server.register_service(0, Description({"foo": True}, server_data_model))
            servers.append(best_server)

            asyncio.get_event_loop().run_until_complete(asyncio.sleep(_ASYNCIO_DELAY))

            query = Query([Constraint("foo", Eq(True))], server_data_model)

            client.search_services(0, query)

            asyncio.get_event_loop().run_until_complete(
                asyncio.gather(
                    client.async_run(),
                    *[server.async_run() for server in servers]
                )
            )

            assert client.group.best_agent == "best_server"
            assert client.group.best_price == 5

            client.disconnect()
            for s in servers:
                s.disconnect()

    def test_group_dialogue_one_client_n_servers_local(self):
        with OEFLocalProxy.LocalNode() as node:
            client_proxy = OEFLocalProxy("client", node)
            client = ClientAgentGroupDialogueTest(client_proxy)
            client.connect()

            N = 10
            server_proxies = [OEFLocalProxy("server_{:02d}".format(i), node) for i in range(N)]
            server_data_model = DataModel("server", [AttributeSchema("foo", bool, True)])

            servers = [ServerAgentTest(server_proxy, price=random.randint(10, 100)) for server_proxy in server_proxies]
            for server in servers:
                server.connect()
                server.register_service(0, Description({"foo": True}, server_data_model))

            best_server = ServerAgentTest(OEFLocalProxy("best_server", node), price=5)
            best_server.connect()
            best_server.register_service(0, Description({"foo": True}, server_data_model))
            servers.append(best_server)

            asyncio.get_event_loop().run_until_complete(asyncio.sleep(_ASYNCIO_DELAY))

            query = Query([Constraint("foo", Eq(True))], server_data_model)

            client.search_services(0, query)

            asyncio.get_event_loop().run_until_complete(
                asyncio.gather(
                    client.async_run(),
                    *[server.async_run() for server in servers]
                )
            )

            assert client.group.best_agent == "best_server"
            assert client.group.best_price == 5

            client.disconnect()
            for s in servers:
                s.disconnect()
