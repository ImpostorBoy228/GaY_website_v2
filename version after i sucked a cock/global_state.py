# global_state.py
import logging

logger = logging.getLogger(__name__)

# Глобальный словарь для хранения состояния задач
tasks = {}

logger.info("Initialized global_state with empty tasks dictionary")