import asyncio
import os
from handlers.conversation import get_graph

async def main():
    os.environ["SQLITE_DB_PATH"] = "pipeline_state.db"
    print("Initializing graph...")
    graph = await get_graph()
    print("Graph initialized:", graph)
    print("Getting state...")
    state = graph.get_state({"configurable": {"thread_id": "test_thread_01"}})
    print("State initialized!", type(state))

if __name__ == "__main__":
    asyncio.run(main())
