import asyncio

import pytest
import zmq.asyncio


@pytest.fixture
def event_loop():
    loop = zmq.asyncio.ZMQEventLoop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def loop(event_loop):
    return event_loop


@pytest.fixture(autouse=True)
def close_context():
    yield
    context = zmq.asyncio.Context.instance()
    context.destroy(linger=0)
