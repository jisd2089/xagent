#!/usr/bin/env python3
"""
Execute task 56 synchronously and print results.
This script is run inside the xAgent container.
"""
import asyncio
import logging
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


async def main():
    from xagent.web.models.database import get_db, SessionLocal
    from xagent.web.models.task import Task, TaskStatus
    from xagent.web.models.user import User
    from xagent.web.api.chat import get_agent_manager
    from xagent.web.services.llm_utils import resolve_llms_from_names
    from xagent.web.api.chat import CoreStorage
    from xagent.web.models.model import Model as DBModel
    from xagent.core.agent.trace import Tracer, ConsoleTraceHandler
    from xagent.core.context import UserContext

    task_id = 56

    # Get database session
    db_gen = SessionLocal()
    db = db_gen

    try:
        # Get task
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.error(f"Task {task_id} not found!")
            return

        logger.info(f"Task {task_id}: title={task.title}, status={task.status.value}")
        logger.info(f"Task agent_id={task.agent_id}, execution_mode={task.execution_mode}")

        # Get user
        user_id = task.user_id
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found!")
            return
        logger.info(f"User: id={user.id}, is_admin={user.is_admin}")

        # Get request object (we need a mock request for agent_manager)
        from fastapi import Request
        from unittest.mock import MagicMock
        mock_request = MagicMock(spec=Request)
        mock_request.app = MagicMock()
        mock_request.app.state = MagicMock()
        mock_request.app.state.agent_manager = None

        # Update task status to RUNNING
        task.status = TaskStatus.RUNNING
        db.commit()

        # Get agent manager
        agent_manager = get_agent_manager(mock_request)

        with UserContext(int(user.id)):
            # Get agent for task
            logger.info(f"Getting agent for task {task_id}...")
            agent_service = await agent_manager.get_agent_for_task(
                task_id, db, user=user
            )

            # Get task description
            task_description = task.description or task.title

            # Execute task
            logger.info(f"Executing task {task_id} with description: {task_description[:100]}...")
            result = await agent_manager.execute_task(
                agent_service=agent_service,
                task=task_description,
                context={},
                task_id=str(task_id),
                tracking_task_id=str(task_id),
                db_session=db,
            )

            logger.info(f"Task execution completed!")
            logger.info(f"Result success: {result.get('success', False)}")
            logger.info(f"Result keys: {list(result.keys())}")

            # Get AI response
            chat_response = result.get("chat_response")
            if isinstance(chat_response, dict):
                ai_response = chat_response.get("message") or result.get("output", "No output")
            else:
                ai_response = result.get("output", "No output")

            logger.info(f"AI Response: {ai_response[:500]}...")
            print("\n\n=== FULL OUTPUT ===\n")
            print(ai_response)

            # Update task status
            if result.get("success", False):
                task.status = TaskStatus.COMPLETED
            else:
                task.status = TaskStatus.FAILED
            db.commit()
            logger.info(f"Task {task_id} status updated to: {task.status.value}")

    except Exception as e:
        logger.error(f"Task execution failed: {e}", exc_info=True)
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED
                db.commit()
        except:
            pass
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
