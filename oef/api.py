# Copyright (C) Fetch.ai 2018 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential

"""
Python bindings for OEFCore
"""

import asyncio
import logging

import oef.agent_pb2 as agent_pb2
import oef.fipa_pb2 as fipa_pb2

import struct

from typing import List, Optional, Union, Awaitable, Tuple

from oef.schema import Description
from oef.query import Query

logger = logging.getLogger(__name__)


class Conversation(object):
    """
    A conversation
    """


NoneType = type(None)
CFP_TYPES = Union[Query, bytes, NoneType]
PROPOSE_TYPES = Union[bytes, List[Description]]

DEFAULT_OEF_NODE_PORT = 3333

class OEFProxy(object):
    """
    Proxy to the functionality of the OEF. Provides functionality for an agent to:
     * Register a description of itself
     * Register its services
     * Locate other agents
     * Locate other services
     * Establish a connection with another agent
    """

    def __init__(self, public_key: str, host_path: str, port: int = DEFAULT_OEF_NODE_PORT) -> None:
        """
        :param host_path: the path to the host
        """
        self._public_key = public_key
        self._host_path = host_path
        self._port = port

        # these are setup in _connect_to_server
        self._connection = None
        self._server_reader = None
        self._server_writer = None

    async def _connect_to_server(self, event_loop) -> Awaitable[Tuple[asyncio.StreamReader, asyncio.StreamWriter]]:
        return await asyncio.open_connection(self._host_path, self._port, loop=event_loop)

    def _send(self, protobuf_msg):  # async too ?
        serialized_msg = protobuf_msg.SerializeToString()
        nbytes = struct.pack("I", len(serialized_msg))
        self._server_writer.write(nbytes)
        self._server_writer.write(serialized_msg)

    async def _receive(self):
        nbytes_packed = await self._server_reader.read(len(struct.pack("I", 0)))
        # print("received ${0}".format(nbytes_packed))
        nbytes = struct.unpack("I", nbytes_packed)
        # print("received unpacked ${0}".format(nbytes[0]))
        # print("Preparing to receive ${0} bytes ...".format(nbytes[0]))
        return await self._server_reader.read(nbytes[0])

    async def connect(self) -> bool:
        event_loop = asyncio.get_event_loop()
        self._connection = await self._connect_to_server(event_loop)
        self._server_reader, self._server_writer = self._connection
        # Step 1: Agent --(ID)--> OEFCore
        pb_public_key = agent_pb2.Agent.Server.ID()
        pb_public_key.public_key = self._public_key
        self._send(pb_public_key)
        # Step 2: OEFCore --(Phrase)--> Agent
        data = await self._receive()
        pb_phrase = agent_pb2.Server.Phrase()
        pb_phrase.ParseFromString(data)
        case = pb_phrase.WhichOneof("payload")
        if case == "failure":
            return False
        # Step 3: Agent --(Answer)--> OEFCore
        pb_answer = agent_pb2.Agent.Server.Answer()
        pb_answer.answer = pb_phrase.phrase[::-1]
        self._send(pb_answer)
        # Step 4: OEFCore --(Connected)--> Agent
        data = await self._receive()
        pb_status = agent_pb2.Server.Connected()
        pb_status.ParseFromString(data)
        return pb_status.status

    async def loop(self, agent) -> None:    # noqa: C901
        # param: OEFAgent

        while True:
            data = await self._receive()
            msg = agent_pb2.Server.AgentMessage()
            msg.ParseFromString(data)
            case = msg.WhichOneof("payload")
            # print("loop {0}".format(case))
            if case == "agents":
                agent.on_search_result(msg.agents.agents)
            elif case == "error":
                agent.on_error(msg.error.operation, msg.error.conversation_id, msg.error.msgid)
            elif case == "content":
                content_case = msg.content.WhichOneof("payload")
                logger.debug("msg content {0}".format(content_case))
                if content_case == "content":
                    agent.on_message(msg.content.origin, msg.content.conversation_id, msg.content.content)
                elif content_case == "fipa":
                    fipa = msg.content.fipa
                    fipa_case = fipa.WhichOneof("msg")
                    if fipa_case == "cfp":
                        cfp_case = fipa.cfp.WhichOneof("payload")
                        if cfp_case == "nothing":
                            query = None
                        elif cfp_case == "content":
                            query = fipa.cfp.content
                        elif cfp_case == "query":
                            query = Query.from_pb(fipa.cfp.query)
                        agent.on_cfp(msg.content.origin, msg.content.conversation_id, fipa.msg_id, fipa.target, query)
                    elif fipa_case == "propose":
                        propose_case = fipa.propose.WhichOneof("payload")
                        if propose_case == "content":
                            proposals = fipa.propose.content
                        else:
                            proposals = [Description.from_pb(propose) for propose in fipa.propose.proposals.objects]
                        agent.on_propose(msg.content.origin, msg.content.conversation_id, fipa.msg_id, fipa.target,
                                        proposals)
                    elif fipa_case == "accept":
                        agent.on_accept(msg.content.origin, msg.content.conversation_id, fipa.msg_id, fipa.target)
                    elif fipa_case == "decline":
                        agent.on_decline(msg.content.origin, msg.content.conversation_id, fipa.msg_id, fipa.target)
                    else:
                        print("Not implemented yet: fipa {0}".format(fipa_case))

    def send_message(self, conversation_id: str, destination: str, msg: bytes):
        agent_msg = agent_pb2.Agent.Message()
        agent_msg.conversation_id = conversation_id
        agent_msg.destination = destination
        agent_msg.content = msg
        envelope = agent_pb2.Envelope()
        envelope.message.CopyFrom(agent_msg)
        self._send(envelope)

    def send_cfp(self, conversation_id: str, destination: str, query: CFP_TYPES, msg_id: Optional[int] = 1,
                 target: Optional[int] = 0):
        fipa_msg = fipa_pb2.Fipa.Message()
        fipa_msg.msg_id = msg_id
        fipa_msg.target = target
        cfp = fipa_pb2.Fipa.Cfp()

        if query is None:
            cfp.nothing.CopyFrom(fipa_pb2.Fipa.Cfp.Nothing())
        elif isinstance(query, Query):
            cfp.query.CopyFrom(query.to_query_pb())
        elif isinstance(query, bytes):
            cfp.content = query
        fipa_msg.cfp.CopyFrom(cfp)
        agent_msg = agent_pb2.Agent.Message()
        agent_msg.conversation_id = conversation_id
        agent_msg.destination = destination
        agent_msg.fipa.CopyFrom(fipa_msg)
        envelope = agent_pb2.Envelope()
        envelope.message.CopyFrom(agent_msg)
        self._send(envelope)

    def send_propose(self, conversation_id: str, destination: str, proposals: PROPOSE_TYPES, msg_id: int,
                     target: Optional[int] = None):
        fipa_msg = fipa_pb2.Fipa.Message()
        fipa_msg.msg_id = msg_id
        fipa_msg.target = target if target is not None else (msg_id - 1)
        propose = fipa_pb2.Fipa.Propose()
        if isinstance(proposals, bytes):
            propose.content = proposals
        else:
            proposals_pb = fipa_pb2.Fipa.Propose.Proposals()
            proposals_pb.objects.extend([propose.as_instance() for propose in proposals])
            propose.proposals.CopyFrom(proposals_pb)
        fipa_msg.propose.CopyFrom(propose)
        agent_msg = agent_pb2.Agent.Message()
        agent_msg.conversation_id = conversation_id
        agent_msg.destination = destination
        agent_msg.fipa.CopyFrom(fipa_msg)
        envelope = agent_pb2.Envelope()
        envelope.message.CopyFrom(agent_msg)
        print("propose envelope {0}".format(envelope))
        self._send(envelope)

    def send_accept(self, conversation_id: str, destination: str, msg_id: int,
                    target: Optional[int] = None):
        fipa_msg = fipa_pb2.Fipa.Message()
        fipa_msg.msg_id = msg_id
        fipa_msg.target = target if target is not None else (msg_id - 1)
        accept = fipa_pb2.Fipa.Accept()
        fipa_msg.accept.CopyFrom(accept)
        agent_msg = agent_pb2.Agent.Message()
        agent_msg.conversation_id = conversation_id
        agent_msg.destination = destination
        agent_msg.fipa.CopyFrom(fipa_msg)
        envelope = agent_pb2.Envelope()
        envelope.message.CopyFrom(agent_msg)
        print("accept envelope {0}".format(envelope))
        self._send(envelope)

    def send_decline(self, conversation_id: str, destination: str, msg_id: int,
                     target: Optional[int] = None):
        fipa_msg = fipa_pb2.Fipa.Message()
        fipa_msg.msg_id = msg_id
        fipa_msg.target = target if target is not None else (msg_id - 1)
        decline = fipa_pb2.Fipa.Decline()
        fipa_msg.accept.CopyFrom(decline)
        agent_msg = agent_pb2.Agent.Message()
        agent_msg.conversation_id = conversation_id
        agent_msg.destination = destination
        agent_msg.fipa.CopyFrom(fipa_msg)
        envelope = agent_pb2.Envelope()
        envelope.message.CopyFrom(agent_msg)
        print("decline envelope {0}".format(envelope))
        self._send(envelope)

    def close(self) -> None:
        """
        Used to tear down resources associated with this Proxy, i.e. the writing connection with
        the server.
        """
        self._server_writer.close()

    def register_agent(self, agent_description: Description) -> bool:
        """
        Adds a description of an agent to the OEF so that it can be understood/ queried by
        other agents in the OEF.

        :param agent_description: description of the agent to add
        :returns: `True` if agent is successfully added, `False` otherwise. Can fail if such an
        agent already exists in the OEF.
        """
        envelope = agent_pb2.Envelope()
        envelope.description.CopyFrom(agent_description.to_pb())
        self._send(envelope)

    def unregister_agent(self, agent_description: Description) -> bool:
        """
        Removes the description of an agent from the OEF. This agent will no longer be queryable
        by other agents in the OEF. A conversation handler must be provided that allows the agent
        to receive and manage conversations from other agents wishing to communicate with it.

        :param agent_description: description of the agent to remove
        :returns: `True` if agent is successfully removed, `False` otherwise. Can fail if
        such an agent is not registered with the OEF.
        """
        pass

    def register_service(self, service_description: Description):
        """
        Adds a description of the respective service so that it can be understood/ queried by
        other agents in the OEF.
        :param service_description: description of the services to add
        :returns: `True` if service is successfully added, `False` otherwise. Can fail if such an
        service already exists in the OEF.
        """
        envelope = agent_pb2.Envelope()
        envelope.register.CopyFrom(service_description.to_pb())
        self._send(envelope)

    def unregister_service(self, service_description: Description) -> None:
        """
        Adds a description of the respective service so that it can be understood/ queried by
        other agents in the OEF.
        :param service_description: description of the services to add
        :returns: `True` if service is successfully added, `False` otherwise. Can fail if such an
        service already exists in the OEF.
        """
        envelope = agent_pb2.Envelope()
        envelope.unregister.CopyFrom(service_description.to_pb())
        self._send(envelope)

    def search_agents(self, query: Query) -> None:
        """
        Allows an agent to search for other agents it is interested in communicating with. This can
        be useful when an agent wishes to directly proposition the provision of a service that it
        thinks another agent may wish to be able to offer it. All matching agents are returned
        (potentially including ourself)
        :param query: specifications of the constraints on the agents that are matched
        :returns: a list of the matching agents
        """
        envelope = agent_pb2.Envelope()
        envelope.search.CopyFrom(query.to_pb())
        self._send(envelope)

    def search_services(self, query: Query) -> None:
        """
        Allows an agent to search for a particular service. This allows constrained search of all
        services that have been registered with the OEF. All matching services will be returned
        (potentially including services offered by ourself)
        :param query: the constraint on the matching services
        """
        envelope = agent_pb2.Envelope()
        envelope.query.CopyFrom(query.to_pb())
        self._send(envelope)

    def start_conversation(self, agent_id: str) -> Conversation:
        """
        Start a conversation with the specified agent. This allows a direct channel of communication
        with an agent.
        """
        pass
