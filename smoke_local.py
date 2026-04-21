"""Local smoke test: start broker first, then: python -m multi_agent_tcp.smoke_local"""

import asyncio

from multi_agent_tcp.client import AgentTCPClient


async def main() -> None:
    a = AgentTCPClient("t1", "127.0.0.1", 9123, "x")
    b = AgentTCPClient("t2", "127.0.0.1", 9123, "x")
    await a.connect()
    await b.connect()
    await a.send_to("t2", {"k": 1})

    async def first_msg(c: AgentTCPClient):
        async for m in c.incoming():
            return m

    m = await asyncio.wait_for(first_msg(b), timeout=3)
    print(m)
    await a.close()
    await b.close()


if __name__ == "__main__":
    asyncio.run(main())
