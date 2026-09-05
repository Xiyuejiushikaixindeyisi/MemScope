#!/usr/bin/env python3
"""Apply the locked MemScope patchset to one exact extracted MemOS v2.0.32 tree."""

import argparse
import hashlib
import json
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCK_PATH = ROOT / "PATCHSET_LOCK.json"


def _replace(text: str, old: str, new: str, *, count: int = 1) -> str:
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"patch anchor count mismatch: expected {count}, got {actual}")
    return text.replace(old, new)


def _simple_struct(text: str) -> str:
    text = _replace(text, "import os\nimport traceback", "import os\nimport time\nimport traceback")
    text = _replace(
        text,
        """    def _safe_generate(self, messages: list[dict]) -> str | None:
        try:
            return self.llm.generate(messages)
        except Exception:
            logger.exception("[LLM] Generation failed")
            return None

    def _safe_parse(self, text: str | None) -> dict | None:
        if not text:
            return None
        try:
            return parse_json_result(text)
        except Exception:
            logger.warning("[LLM] JSON parse failed")
            return None

    def _get_llm_response(self, mem_str: str, custom_tags: list[str] | None) -> dict:
""",
        """    @staticmethod
    def _remaining_timeout(info: dict | None) -> float:
        deadline = (info or {}).get("memscope_deadline_unix_ms")
        if deadline is None:
            return 110.0
        if isinstance(deadline, bool) or not isinstance(deadline, int):
            raise ValueError("invalid MemScope Add deadline")
        remaining = (deadline - int(time.time() * 1000)) / 1000
        if remaining <= 0:
            raise TimeoutError("MemScope Add deadline exceeded")
        return remaining

    def _safe_generate(self, messages: list[dict], *, timeout_seconds: float) -> str:
        result = self.llm.generate(messages, timeout=timeout_seconds)
        if not isinstance(result, str) or not result.strip():
            raise ValueError("LLM returned an empty response")
        return result

    @staticmethod
    def _safe_parse(text: str) -> dict:
        result = parse_json_result(text)
        if not isinstance(result, dict):
            raise ValueError("LLM response is not a JSON object")
        memory_list = result.get("memory list")
        if not isinstance(memory_list, list):
            raise ValueError("LLM response has no memory list")
        for item in memory_list:
            if not isinstance(item, dict):
                raise ValueError("LLM memory item is not an object")
            value = item.get("value")
            memory_type = item.get("memory_type", "LongTermMemory")
            tags = item.get("tags", [])
            key = item.get("key", "")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("LLM memory value is empty")
            if memory_type not in {"LongTermMemory", "UserMemory", "长期记忆", "用户记忆"}:
                raise ValueError("LLM memory type is unsupported")
            if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                raise ValueError("LLM memory tags are invalid")
            if not isinstance(key, str):
                raise ValueError("LLM memory key is invalid")
        if not isinstance(result.get("summary", ""), str):
            raise ValueError("LLM summary is invalid")
        return result

    @staticmethod
    def _deduplicate_exact(groups):
        seen: dict[str, set[str]] = {}
        result = []
        for group in groups:
            kept = []
            for memory in group:
                source_ids = {
                    source_id
                    for source in (memory.metadata.sources or [])
                    if isinstance(
                        source_id := (
                            source.get("message_id")
                            if isinstance(source, dict)
                            else getattr(source, "message_id", None)
                        ),
                        str,
                    )
                }
                prior = seen.get(memory.memory, set())
                if source_ids and prior.intersection(source_ids):
                    continue
                seen.setdefault(memory.memory, set()).update(source_ids)
                kept.append(memory)
            result.append(kept)
        return result

    def _get_llm_response(
        self, mem_str: str, custom_tags: list[str] | None, info: dict | None = None
    ) -> dict:
""",
    )
    start = text.index("        response_text = self._safe_generate(messages)")
    end_marker = "        return response_json\n\n    def _iter_chat_windows"
    end = text.index(end_marker, start)
    text = (
        text[:start]
        + """        timeout_seconds = self._remaining_timeout(info)
        response_text = self._safe_generate(messages, timeout_seconds=timeout_seconds)
        return self._safe_parse(response_text)

    def _iter_chat_windows"""
        + text[end + len(end_marker) :]
    )
    text = _replace(
        text,
        '                    "index": idx,\n                    "role": role,',
        '                    "index": item.get("request_position", idx),\n'
        '                    "message_id": item.get("message_id"),\n                    "role": role,',
    )
    text = _replace(
        text,
        """        windows = list(self._iter_chat_windows(scene_data_info))
        custom_tags = info.pop(
            "custom_tags", None
        )  # must pop here, avoid add to info, only used in sync fine mode
""",
        """        self._remaining_timeout(info)
        windows = list(self._iter_chat_windows(scene_data_info))
        local_info = info.copy()
        custom_tags = local_info.pop("custom_tags", None)
""",
    )
    text = _replace(text, "info=info,", "info=local_info,", count=2)
    text = _replace(
        text,
        '                resp = self._get_llm_response(w["text"], custom_tags)',
        '                resp = self._get_llm_response(w["text"], custom_tags, local_info)',
    )
    text = _replace(
        text,
        """                    except Exception as e:
                        logger.error(f"[ChatFine] parse error: {e}")
            return chat_read_nodes
""",
        """                    except Exception as e:
                        raise ValueError("invalid extracted memory item") from e
            return chat_read_nodes
""",
    )
    text = _replace(
        text,
        "response_json = self._get_llm_response(raw_memory, custom_tags)",
        "response_json = self._get_llm_response(\n"
        "            raw_memory, custom_tags, raw_node.metadata.info or {}\n        )",
    )
    old = """        # Process Q&A pairs concurrently with context propagation
        with ContextThreadPoolExecutor() as executor:
            futures = [
                executor.submit(processing_func, scene_data_info, info, mode=mode)
                for scene_data_info in list_scene_data_info
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    res_memory = future.result()
                    if res_memory is not None:
                        memory_list.append(res_memory)
                except Exception as e:
                    logger.error(f"Task failed with exception: {e}")
                    logger.error(traceback.format_exc())
"""
    new = """        # Process windows concurrently, but publish results in original order.
        self._remaining_timeout(info)
        with ContextThreadPoolExecutor() as executor:
            futures = {
                executor.submit(
                    processing_func,
                    scene_data_info,
                    info.copy(),
                    mode=mode,
                    **kwargs,
                ): index
                for index, scene_data_info in enumerate(list_scene_data_info)
            }
            ordered = [None] * len(futures)
            for future in concurrent.futures.as_completed(futures):
                ordered[futures[future]] = future.result()
        memory_list = [item for item in ordered if item is not None]
        memory_list = self._deduplicate_exact(memory_list)
        self._remaining_timeout(info)
"""
    text = _replace(text, old, new)
    text = _replace(
        text,
        """                            "role": role,
                            "content": content,
                            "chat_time": item.get("chat_time", ""),
""",
        """                            "role": role,
                            "content": content,
                            "chat_time": item.get("chat_time", ""),
                            "message_id": item.get("message_id"),
                            "request_position": _i,
""",
    )
    return text


def _single_cube(text: str) -> str:
    text = _replace(text, "import json\nimport time", "import json\nimport os\nimport time")
    text = _replace(
        text,
        """        self.logger.info(
            f"[DIAGNOSTIC] single_cube.add_memories called for cube_id: {self.cube_id}. sync_mode: {sync_mode}. Request: {add_req.model_dump_json(indent=2)}"
        )
""",
        """        self.logger.info(
            "[SingleCubeView] add started sync_mode=%s message_count=%s",
            sync_mode,
            len(add_req.messages or []),
        )
""",
    )
    text = _replace(
        text,
        """        self.logger.info(
            f"[SingleCubeView] cube={self.cube_id} "
            f"Processing add with mode={sync_mode}, session={target_session_id}"
        )
""",
        """        self.logger.info("[SingleCubeView] processing add mode=%s", sync_mode)
""",
    )
    text = _replace(
        text,
        '        self.logger.info(f"[SingleCubeView] cube={self.cube_id} total_results={len(all_memories)}")',
        '        self.logger.info("[SingleCubeView] add completed count=%s", len(all_memories))',
    )
    text = _replace(
        text,
        """        self.logger.info(
            "[SingleCubeView] cube=%s Processing text memory "
            "with sync_mode=%s, extract_mode=%s, add_mode=%s",
            user_context.mem_cube_id,
            sync_mode,
            extract_mode,
            add_req.mode,
        )
""",
        """        self.logger.info(
            "[SingleCubeView] processing text memory sync_mode=%s extract_mode=%s",
            sync_mode,
            extract_mode,
        )
""",
    )
    text = _replace(
        text,
        """        target_session_id = add_req.session_id or "default_session"

        if sync_mode == "async":
""",
        """        target_session_id = add_req.session_id or "default_session"

        if (
            os.getenv("MOS_ENABLE_SCHEDULER", "false").lower() != "true"
            and os.getenv("API_SCHEDULER_ON", "false").lower() != "true"
        ):
            self.logger.info("[SingleCubeView] scheduler disabled")
            return

        if sync_mode == "async":
""",
    )
    text = _replace(
        text,
        """        mem_group = [
            memory for memory in flattened_local if memory.metadata.memory_type != "RawFileMemory"
        ]

        # Stage 3: write_db
""",
        """        mem_group = [
            memory for memory in flattened_local if memory.metadata.memory_type != "RawFileMemory"
        ]
        request_info = add_req.info or {}
        result_count = len(mem_group)
        session_start = request_info.get("memscope_session_start_position")
        for result_index, memory in enumerate(mem_group):
            memory_info = dict(memory.metadata.info or {})
            source_positions = sorted(
                {
                    source.get("index")
                    if isinstance(source, dict)
                    else getattr(source, "index", None)
                    for source in (memory.metadata.sources or [])
                    if isinstance(
                        source.get("index")
                        if isinstance(source, dict)
                        else getattr(source, "index", None),
                        int,
                    )
                }
            )
            memory_info.update(
                {
                    "memscope_cube_id": self.cube_id,
                    "memscope_result_index": result_index,
                    "memscope_result_count": result_count,
                    "memscope_source_positions": source_positions,
                    "memscope_session_positions": [
                        session_start + position for position in source_positions
                    ]
                    if isinstance(session_start, int)
                    else [],
                }
            )
            memory.metadata.info = memory_info

        deadline = request_info.get("memscope_deadline_unix_ms")
        if isinstance(deadline, bool) or not isinstance(deadline, int):
            raise ValueError("missing MemScope Add deadline")
        if int(time.time() * 1000) >= deadline:
            raise TimeoutError("MemScope Add deadline exceeded before write")

        # Stage 3: write_db
""",
    )
    text = _replace(
        text,
        """            self.logger.info(
                f"Added {len(mem_ids_local)} memories for user {add_req.user_id} "
                f"in session {add_req.session_id}: {mem_ids_local}"
            )
""",
        """            if len(mem_ids_local) != len(mem_group):
                raise RuntimeError("memory persistence count mismatch")
            self.logger.info("Added %s memories", len(mem_ids_local))
""",
    )
    text = _replace(
        text,
        'with timed_stage("add", "get_memory", cube_id=self.cube_id)',
        'with timed_stage("add", "get_memory", cube_configured=True)',
    )
    text = _replace(
        text,
        'with timed_stage("add", "write_db", cube_id=self.cube_id)',
        'with timed_stage("add", "write_db", cube_configured=True)',
    )
    text = _replace(
        text,
        'with timed_stage("add", "schedule", cube_id=self.cube_id)',
        'with timed_stage("add", "schedule", cube_configured=True)',
    )
    text = _replace(text, "            cube_id=self.cube_id,", "            cube_configured=True,")
    text = _replace(
        text,
        '        logger.info(f"Found {len(formatted_memories)} memories for user {search_req.user_id}")',
        '        logger.info("Found %s memories", len(formatted_memories))',
    )
    text = _replace(
        text,
        '                logger.info(f"Triggering additional search with hint: {missing_info_hint}")',
        '                logger.info("Triggering additional Search")',
    )
    text = _replace(
        text,
        "                    f\"[add_before_search] Search error for memory '{mem.memory}': {e}\"",
        '                    "[add_before_search] Search failed"',
    )
    text = _replace(
        text,
        """        try:
            if search_mode == SearchMode.FAST:
                text_memories = self._fast_search(search_req, user_context)
            elif search_mode == SearchMode.FINE:
                text_memories = self._fine_search(search_req, user_context)
            elif search_mode == SearchMode.MIXTURE:
                text_memories = self._mix_search(search_req, user_context)
            else:
                self.logger.error(f"Unsupported search mode: {search_mode}")
                return []
            return text_memories

        except Exception as e:
            self.logger.error("Error in search_text: %s; traceback: %s", e, traceback.format_exc())
            return []
""",
        """        if search_mode == SearchMode.FAST:
            return self._fast_search(search_req, user_context)
        if search_mode == SearchMode.FINE:
            return self._fine_search(search_req, user_context)
        if search_mode == SearchMode.MIXTURE:
            return self._mix_search(search_req, user_context)
        raise ValueError("unsupported Search mode")
""",
    )
    text = _replace(text, "import traceback\n", "")
    return text


def _searcher(text: str) -> str:
    text = _replace(
        text,
        """        logger.info(
            f"[RECALL] Start query='{query}', top_k={top_k}, mode={mode}, memory_type={memory_type}, user_name={user_name}"
        )
""",
        """        logger.info(
            "[RECALL] Start query_chars=%s top_k=%s mode=%s memory_type=%s",
            len(query),
            top_k,
            mode,
            memory_type,
        )
""",
    )
    text = _replace(
        text,
        '            logger.debug(f"[SEARCH] Received info dict: {info}")',
        '            logger.debug("[SEARCH] Received bounded request metadata")',
    )
    text = _replace(
        text,
        '                    logger.error(f"[SEARCH] Error during search: {traceback.format_exc()}")',
        '                    logger.error("[SEARCH] Candidate conversion failed")',
    )
    text = _replace(
        text,
        '            logger.info(f"[SEARCH] Retrieve from plugin: {query}")',
        '            logger.info("[SEARCH] Retrieve from plugin query_chars=%s", len(query))',
    )
    text = _replace(
        text,
        "            logger.info(f\"[PATH-A] '{query}'Skipped (memory_type does not match)\")",
        '            logger.info("[PATH-A] Skipped (memory_type does not match)")',
    )
    for old, new in (
        (
            "            logger.info(f\"[PATH-C] '{query}' Skipped (no retriever)\")",
            '            logger.info("[PATH-C] Skipped (no retriever)")',
        ),
        (
            "            logger.info(f\"[PATH-C] '{query}' Skipped (no retriever, fast mode)\")",
            '            logger.info("[PATH-C] Skipped (no retriever, fast mode)")',
        ),
        (
            "            logger.info(f\"[PATH-C] '{query}' Skipped (memory_type does not match)\")",
            '            logger.info("[PATH-C] Skipped (memory_type does not match)")',
        ),
        (
            "        logger.info(f\"[PATH-C] '{query}' Retrieving from internet...\")",
            '        logger.info("[PATH-C] Retrieving from internet")',
        ),
        (
            "        logger.info(f\"[PATH-C] '{query}' Retrieved from internet {len(items)} items: {items}\")",
            '        logger.info("[PATH-C] Retrieved from internet count=%s", len(items))',
        ),
        (
            "            logger.info(f\"[PATH-E] '{query}' Skipped (memory_type does not match)\")",
            '            logger.info("[PATH-E] Skipped (memory_type does not match)")',
        ),
        (
            "            logger.info(f\"[PATH-F] '{query}' Skipped (memory_type does not match)\")",
            '            logger.info("[PATH-F] Skipped (memory_type does not match)")',
        ),
        (
            '        logger.info(f"[SIMPLESEARCH] Query words: {query_words}")',
            '        logger.info("[SIMPLESEARCH] Query term count=%s", len(query_words))',
        ),
        (
            '                logger.info("Query: {} COT: {}".format(query, response_json["sub_questions"]))',
            '                logger.info("COT split count=%s", len(response_json["sub_questions"]))',
        ),
        (
            '        except Exception as e:\n            logger.error(f"[LLM] Exception during chat generation: {e}")',
            '        except Exception:\n            logger.error("[LLM] Chat generation failed")',
        ),
    ):
        text = _replace(text, old, new)
    text = _replace(text, "import traceback\n", "")
    return text


def _task_goal_parser(text: str) -> str:
    text = _replace(
        text,
        '            logger.info(f"Parsing Goal... LLM input is {prompt}")',
        """            logger.info(
                "Parsing Goal query_chars=%s context_chars=%s conversation_count=%s",
                len(query),
                len(context),
                len(conversation or []),
            )""",
    )
    text = _replace(
        text,
        '            logger.info(f"Parsing Goal... LLM Response is {response}")',
        '            logger.info("Parsing Goal response received")',
    )
    text = _replace(
        text,
        '            logger.warning(f"Fail to fine-parse query {query}: {traceback.format_exc()}")',
        '            logger.warning("Fine goal parsing failed; using fast mode")',
    )
    text = _replace(
        text,
        '                        f"Failed to parse LLM output: {e}\\nRaw response:\\n{response} retried: {attempt_times + 1}/{attempts}"',
        '                        f"Failed to parse LLM output after {attempt_times + 1}/{attempts} attempts"',
    )
    text = _replace(text, "import traceback\n\n", "")
    return text


def _retrieve_utils(text: str) -> str:
    text = _replace(
        text,
        '    except json.JSONDecodeError as e:\n        logger.error(f"[JSONParse] Failed to decode JSON: {e}\\nRaw:\\n{response_text}")',
        '    except json.JSONDecodeError:\n        logger.error("[JSONParse] Failed to decode JSON response")',
    )
    text = _replace(
        text,
        '    except Exception as e:\n        logger.error(f"[JSONParse] Unexpected error: {e}")',
        '    except Exception:\n        logger.error("[JSONParse] Unexpected response parsing error")',
    )
    return text


def _manager(text: str) -> str:
    return _replace(
        text,
        """                    except Exception as e:
                        logger.exception(
                            f"Batch add {node_kind} nodes error (batch {idx}, size {size}): ",
                            exc_info=e,
                        )
""",
        """                    except Exception:
                        logger.exception(
                            "Batch add failed for kind=%s batch=%s size=%s",
                            node_kind,
                            idx,
                            size,
                        )
                        raise
""",
    )


def _openai(text: str) -> str:
    text = _replace(
        text,
        "api_key=config.api_key, base_url=config.api_base, default_headers=config.default_headers",
        "api_key=config.api_key, base_url=config.api_base, "
        "default_headers=config.default_headers, timeout=config.timeout_seconds",
    )
    text = _replace(
        text,
        """        log_extra_args=lambda self, messages, **kwargs: {
            "model_name_or_path": kwargs.get("model_name_or_path", self.config.model_name_or_path),
            "messages": messages,
        },
""",
        """        log_extra_args=lambda self, messages, **kwargs: {
            "message_count": len(messages),
        },
""",
    )
    text = _replace(
        text,
        '            "extra_body": extra_body,\n'
        '            "tools": kwargs.get("tools", NOT_GIVEN),\n',
        '            "extra_body": extra_body,\n'
        '            "tools": kwargs.get("tools", NOT_GIVEN),\n'
        '            "timeout": kwargs.get("timeout", self.config.timeout_seconds),\n',
    )
    text = _replace(text, '        logger.info(f"OpenAI LLM Request body: {request_body}")\n', "")
    text = _replace(
        text,
        """            logger.info(
                f"Request body: {request_body}, Response from OpenAI: "
                f"{response.model_dump_json()}, Cost time: {cost_time}"
            )
""",
        """            logger.info("OpenAI LLM request succeeded in %.3f seconds", cost_time)
""",
    )
    text = _replace(
        text,
        """            if not self.use_backup_client:
                raise
            logger.warning(
                f"Primary LLM request failed with {type(e).__name__}: {e}, "
                f"falling back to backup client"
            )
""",
        """            if not self.use_backup_client:
                raise RuntimeError("LLM request failed") from None
            logger.warning("Primary LLM request failed; using configured backup")
""",
    )
    text = _replace(
        text,
        """            logger.info(
                f"Backup LLM request succeeded, Response: "
                f"{backup_response.model_dump_json()}, Cost time: {cost_time}"
            )
""",
        """            logger.info("Backup LLM request succeeded in %.3f seconds", cost_time)
""",
    )
    text = _replace(
        text, '        logger.info(f"OpenAI LLM Stream Request body: {request_body}")\n', ""
    )
    return text


def _llm_config(text: str) -> str:
    return _replace(
        text,
        """    extra_body: Any = Field(default=None, description="extra body")
    enable_thinking: bool | None = Field(
""",
        """    extra_body: Any = Field(default=None, description="extra body")
    timeout_seconds: float = Field(default=110.0, gt=0, le=115)
    enable_thinking: bool | None = Field(
""",
    )


def _add_handler(text: str) -> str:
    return _replace(
        text,
        """        self.logger.info(
            f"[DIAGNOSTIC] server_router -> add_handler.handle_add_memories called (Modified at 2025-11-29 18:46). Full request: {add_req.model_dump_json(indent=2)}"
        )
""",
        """        self.logger.info(
            "[AddHandler] request received message_count=%s mode=%s async_mode=%s",
            len(add_req.messages or []),
            add_req.mode,
            add_req.async_mode,
        )
""",
    )


def _api_config(text: str) -> str:
    text = _replace(
        text,
        '"tokenizer_or_token_counter": "gpt2"',
        '"tokenizer_or_token_counter": os.getenv("MEM_READER_TOKENIZER", "word")',
        count=3,
    )
    text = _replace(
        text,
        """            "api_base": os.getenv("MEMRADER_API_BASE", "https://api.openai.com/v1"),
            "remove_think_prefix": True,
""",
        """            "api_base": os.getenv("MEMRADER_API_BASE", "https://api.openai.com/v1"),
            "remove_think_prefix": True,
            "timeout_seconds": float(os.getenv("MEMRADER_TIMEOUT_SECONDS", "110")),
""",
    )
    text = _replace(
        text,
        """        }

        general_model = os.getenv("MEMREADER_GENERAL_MODEL")
""",
        """        }

        thinking_type = os.getenv("MEMRADER_THINKING_TYPE", "").strip().lower()
        if thinking_type and thinking_type not in {"enabled", "disabled"}:
            raise ValueError("MEMRADER_THINKING_TYPE must be enabled or disabled")
        response_format = os.getenv("MEMRADER_RESPONSE_FORMAT", "").strip().lower()
        if response_format and response_format != "json_object":
            raise ValueError("MEMRADER_RESPONSE_FORMAT must be json_object")
        extra_body = {}
        if thinking_type:
            extra_body["thinking"] = {"type": thinking_type}
        if response_format:
            extra_body["response_format"] = {"type": response_format}
        if extra_body:
            config["extra_body"] = extra_body

        general_model = os.getenv("MEMREADER_GENERAL_MODEL")
""",
        count=1,
    )
    text = _replace(
        text,
        '                    "embedding_dims": int(os.getenv("EMBEDDING_DIMENSION", "1024")),\n',
        '                    "embedding_dims": int(os.getenv("EMBEDDING_DIMENSION", "1024")),\n'
        '                    "send_dimensions": os.getenv(\n'
        '                        "MOS_EMBEDDER_SEND_DIMENSIONS", "true"\n'
        "                    ).lower()\n"
        '                    == "true",\n',
    )
    text = _replace(
        text,
        """                    "url": os.getenv("MOS_RERANKER_URL", "localhost:8000/v1/rerank"),
                    "model": os.getenv("MOS_RERANKER_MODEL", "bge-reranker-v2-m3"),
                    "timeout": 10,
""",
        """                    "url": os.getenv("MOS_RERANKER_URL", "localhost:8000/v1/rerank"),
                    "token": os.getenv("MOS_RERANKER_API_KEY", ""),
                    "model": os.getenv("MOS_RERANKER_MODEL", "bge-reranker-v2-m3"),
                    "timeout": int(os.getenv("MOS_RERANKER_TIMEOUT_SECONDS", "10")),
                    "max_retries": int(os.getenv("MOS_RERANKER_MAX_RETRIES", "1")),
                    "retry_backoff_seconds": float(
                        os.getenv("MOS_RERANKER_RETRY_BACKOFF_SECONDS", "0.25")
                    ),
""",
        count=1,
    )
    text = _replace(
        text,
        """                    "url": os.getenv("MOS_RERANKER_URL", "localhost:8000/v1/rerank"),
                    "model": os.getenv("MOS_FEEDBACK_RERANKER_MODEL", "bge-reranker-v2-m3"),
                    "timeout": 10,
""",
        """                    "url": os.getenv("MOS_RERANKER_URL", "localhost:8000/v1/rerank"),
                    "token": os.getenv("MOS_RERANKER_API_KEY", ""),
                    "model": os.getenv("MOS_FEEDBACK_RERANKER_MODEL", "bge-reranker-v2-m3"),
                    "timeout": int(os.getenv("MOS_RERANKER_TIMEOUT_SECONDS", "10")),
                    "max_retries": int(os.getenv("MOS_RERANKER_MAX_RETRIES", "1")),
                    "retry_backoff_seconds": float(
                        os.getenv("MOS_RERANKER_RETRY_BACKOFF_SECONDS", "0.25")
                    ),
""",
        count=1,
    )
    text = _replace(
        text,
        """                    "chat_chunker": reader_config,
                    "direct_markdown_hostnames": [
""",
        """                    "chat_chunker": reader_config,
                    "chat_window_max_tokens": int(
                        os.getenv("MEM_READER_CHAT_WINDOW_MAX_TOKENS", "1024")
                    ),
                    "remove_prompt_example": os.getenv(
                        "MEM_READER_REMOVE_PROMPT_EXAMPLE", "false"
                    ).lower()
                    == "true",
                    "direct_markdown_hostnames": [
""",
        count=1,
    )
    text = _replace(
        text,
        """                    "chat_chunker": reader_config,
                },
""",
        """                    "chat_chunker": reader_config,
                    "chat_window_max_tokens": int(
                        os.getenv("MEM_READER_CHAT_WINDOW_MAX_TOKENS", "1024")
                    ),
                    "remove_prompt_example": os.getenv(
                        "MEM_READER_REMOVE_PROMPT_EXAMPLE", "false"
                    ).lower()
                    == "true",
                },
""",
        count=1,
    )
    return text


def _embedder_config(text: str) -> str:
    return _replace(
        text,
        """    backup_client: bool = Field(
        default=False,
        description="Whether to use backup client",
    )
""",
        """    send_dimensions: bool = Field(
        default=True,
        description="Whether to send the dimensions parameter to the provider",
    )
    backup_client: bool = Field(
        default=False,
        description="Whether to use backup client",
    )
""",
    )


def _universal_api_embedder(text: str) -> str:
    text = _replace(
        text,
        """        embedding_dims = getattr(self.config, "embedding_dims", None)
        kwargs = self._build_embedding_kwargs(model, texts, embedding_dims)

        try:
            response = client.embeddings.create(**kwargs, timeout=timeout)
        except BadRequestError as error:
            if embedding_dims is None or not self._is_dimensions_unsupported(error):
                raise

            logger.warning(
                "Embedding provider rejected dimensions=%d; retrying without dimensions",
                embedding_dims,
            )
            fallback_kwargs = self._build_embedding_kwargs(model, texts, None)
            response = client.embeddings.create(**fallback_kwargs, timeout=timeout)

        return [item.embedding for item in response.data]
""",
        """        embedding_dims = getattr(self.config, "embedding_dims", None)
        request_embedding_dims = (
            embedding_dims if self.config.send_dimensions else None
        )
        kwargs = self._build_embedding_kwargs(model, texts, request_embedding_dims)

        try:
            response = client.embeddings.create(**kwargs, timeout=timeout)
        except BadRequestError as error:
            if request_embedding_dims is None or not self._is_dimensions_unsupported(error):
                raise

            logger.warning(
                "Embedding provider rejected configured dimensions; retrying without it"
            )
            fallback_kwargs = self._build_embedding_kwargs(model, texts, None)
            response = client.embeddings.create(**fallback_kwargs, timeout=timeout)

        vectors = [item.embedding for item in response.data]
        if len(vectors) != len(texts):
            raise ValueError("embedding response count mismatch")
        if embedding_dims is not None and any(
            not hasattr(vector, "__len__") or len(vector) != embedding_dims
            for vector in vectors
        ):
            raise ValueError("embedding response dimension mismatch")
        return vectors
""",
    )
    text = _replace(
        text,
        """                        raise ValueError(
                            f"Backup embeddings request ended with error: {e_backup}"
                        ) from e_backup
                else:
                    raise ValueError(f"Embeddings request ended with error: {e}") from e
""",
        """                        raise ValueError("Backup embeddings request failed") from None
                else:
                    raise ValueError("Embeddings request failed") from None
""",
    )
    text = _replace(
        text,
        "                    except Exception as e_backup:\n",
        "                    except Exception:\n",
    )
    return text


def _reranker_factory(text: str) -> str:
    text = _replace(
        text,
        """        if backend in {"http_bge", "bge"}:
            return HTTPBGEReranker(
                reranker_url=c.get("url") or c.get("endpoint") or c.get("reranker_url"),
                model=c.get("model", "bge-reranker-v2-m3"),
                timeout=int(c.get("timeout", 10)),
""",
        """        if backend in {"http_bge", "bge"}:
            return HTTPBGEReranker(
                reranker_url=c.get("url") or c.get("endpoint") or c.get("reranker_url"),
                token=c.get("token", ""),
                model=c.get("model", "bge-reranker-v2-m3"),
                timeout=int(c.get("timeout", 10)),
                max_retries=int(c.get("max_retries", 1)),
                retry_backoff_seconds=float(c.get("retry_backoff_seconds", 0.25)),
""",
    )
    return text


def _http_bge(text: str) -> str:
    text = _replace(text, "import re\n", "import math\nimport re\nimport time\n")
    text = _replace(
        text,
        """    - If the service fails or responds unexpectedly, this falls back to
      returning the original items with 0.0 scores (best-effort).
""",
        """    - Provider, transport and response-schema failures are propagated so
      callers cannot mistake an unavailable reranker for a successful ranking.
""",
    )
    text = _replace(
        text,
        """        timeout: int = 10,
        max_query_tokens: int | None = None,
""",
        """        timeout: int = 10,
        max_retries: int = 1,
        retry_backoff_seconds: float = 0.25,
        max_query_tokens: int | None = None,
""",
    )
    text = _replace(
        text,
        """        self.timeout = timeout
        self.max_query_tokens = max_query_tokens
""",
        """        self.timeout = timeout
        self.max_retries = min(max(0, int(max_retries)), 2)
        self.retry_backoff_seconds = min(max(0.0, float(retry_backoff_seconds)), 1.0)
        self.max_query_tokens = max_query_tokens
""",
    )
    text = _replace(
        text,
        """        self.warn_unknown_filter_keys = bool(warn_unknown_filter_keys)
        self._warned_missing_keys: set[str] = set()

    @timed_with_status(
""",
        """        self.warn_unknown_filter_keys = bool(warn_unknown_filter_keys)
        self._warned_missing_keys: set[str] = set()

    @staticmethod
    def _validated_score(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("reranker relevance score is invalid")
        score = float(value)
        if not math.isfinite(score):
            raise ValueError("reranker relevance score is invalid")
        return score

    @timed_with_status(
""",
    )
    text = _replace(
        text,
        """    @timed_with_status(
        log_prefix="model_timed_rerank",
        log_extra_args={"model_name_or_path": "reranker"},
        fallback=lambda exc, self, query, graph_results, top_k, *a, **kw: [
            (item, 0.0) for item in graph_results[:top_k]
        ],
    )
""",
        """    @timed_with_status(
        log_prefix="model_timed_rerank",
        log_extra_args={"model_name_or_path": "reranker"},
    )
""",
    )
    text = _replace(
        text,
        """        if not graph_results:
            return []
""",
        """        if top_k <= 0 or not graph_results:
            return []
""",
    )
    text = _replace(
        text,
        '        logger.info(f"[HTTPBGERerankerSample] query: {query} , documents: {documents[:5]}...")\n',
        """        logger.info(
            "Reranker request query_chars=%s document_count=%s",
            len(query),
            len(documents),
        )
""",
    )
    text = _replace(
        text,
        """        headers = {"Content-Type": "application/json", **self.headers_extra}
        payload = {"model": self.model, "query": query, "documents": documents}

        # Make the HTTP request to the reranker service
        resp = requests.post(self.reranker_url, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
""",
        """        headers = {"Content-Type": "application/json", **self.headers_extra}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": min(top_k, len(documents)),
            "return_documents": False,
        }

        retryable_statuses = {429, 503, 504}
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(
                    self.reranker_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.Timeout:
                if attempt >= self.max_retries:
                    raise TimeoutError("reranker request timed out") from None
                logger.warning("Reranker request timed out; retrying attempt=%s", attempt + 2)
                time.sleep(self.retry_backoff_seconds * (attempt + 1))
                continue
            except requests.RequestException:
                if attempt >= self.max_retries:
                    raise ConnectionError("reranker request failed") from None
                logger.warning("Reranker transport failed; retrying attempt=%s", attempt + 2)
                time.sleep(self.retry_backoff_seconds * (attempt + 1))
                continue

            if resp.status_code in retryable_statuses and attempt < self.max_retries:
                logger.warning(
                    "Reranker retryable HTTP status=%s attempt=%s",
                    resp.status_code,
                    attempt + 2,
                )
                time.sleep(self.retry_backoff_seconds * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"reranker request failed with HTTP {resp.status_code}"
                ) from None
            break

        try:
            data = resp.json()
        except ValueError:
            raise ValueError("invalid reranker JSON response") from None
        if not isinstance(data, dict):
            raise ValueError("unexpected reranker response schema")
        trace_id = resp.headers.get("x-siliconcloud-trace-id", "absent")
        logger.info(
            "Reranker request succeeded status=%s document_count=%s trace_id=%s",
            resp.status_code,
            len(documents),
            trace_id,
        )
""",
    )
    text = _replace(
        text,
        """            rows = data.get("results", [])
            for r in rows:
                idx = r.get("index")
                # The returned index refers to 'documents' (i.e., our 'pairs' order),
                # so we must map it back to the original graph_results index.
                if isinstance(idx, int) and 0 <= idx < len(graph_results):
                    raw_score = float(r.get("relevance_score", r.get("score", 0.0)))
                    item = graph_results[idx]
                    # generic boost
                    score = self._apply_boost_generic(item, raw_score, search_priority)
                    scored_items.append((item, score))

            scored_items.sort(key=lambda x: x[1], reverse=True)
            return scored_items[: min(top_k, len(scored_items))]
""",
        """            rows = data.get("results")
            if not isinstance(rows, list) or not rows:
                raise ValueError("unexpected reranker response schema")
            seen_indices: set[int] = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("unexpected reranker response schema")
                idx = row.get("index")
                if (
                    isinstance(idx, bool)
                    or not isinstance(idx, int)
                    or not 0 <= idx < len(graph_results)
                    or idx in seen_indices
                ):
                    raise ValueError("unexpected reranker response schema")
                seen_indices.add(idx)
                raw_score = self._validated_score(row.get("relevance_score"))
                item = graph_results[idx]
                score = self._apply_boost_generic(item, raw_score, search_priority)
                scored_items.append((item, score))

            scored_items.sort(key=lambda x: x[1], reverse=True)
            return scored_items[: min(top_k, len(scored_items))]
""",
    )
    text = _replace(
        text,
        """            rows = data.get("data", [])
            # Build a list of scores aligned with our 'documents' (pairs)
            score_list = [float(r.get("score", 0.0)) for r in rows]

            if len(score_list) < len(graph_results):
                score_list += [0.0] * (len(graph_results) - len(score_list))
            elif len(score_list) > len(graph_results):
                score_list = score_list[: len(graph_results)]
""",
        """            rows = data.get("data")
            if (
                not isinstance(rows, list)
                or len(rows) != len(graph_results)
                or not all(isinstance(row, dict) for row in rows)
            ):
                raise ValueError("unexpected reranker response schema")
            score_list = [self._validated_score(row.get("score")) for row in rows]
""",
    )
    text = _replace(
        text,
        """        else:
            # Unexpected response schema: return a 0.0-scored fallback of the first top_k valid docs
            # Note: we use 'pairs' to keep alignment with valid (string) docs.
            return [(item, 0.0) for item in graph_results[:top_k]]
""",
        """        else:
            raise ValueError("unexpected reranker response schema")
""",
    )
    return text


def _rabbitmq(text: str) -> str:
    return _replace(
        text,
        "if self._io_loop_thread and self._io_loop_thread.is_alive():",
        'if getattr(self, "_io_loop_thread", None) and self._io_loop_thread.is_alive():',
    )


PATCHES: dict[str, Callable[[str], str]] = {
    "src/memos/mem_reader/simple_struct.py": _simple_struct,
    "src/memos/multi_mem_cube/single_cube.py": _single_cube,
    "src/memos/memories/textual/tree_text_memory/retrieve/searcher.py": _searcher,
    "src/memos/memories/textual/tree_text_memory/retrieve/task_goal_parser.py": (_task_goal_parser),
    "src/memos/memories/textual/tree_text_memory/retrieve/retrieve_utils.py": (_retrieve_utils),
    "src/memos/memories/textual/tree_text_memory/organize/manager.py": _manager,
    "src/memos/llms/openai.py": _openai,
    "src/memos/configs/llm.py": _llm_config,
    "src/memos/configs/embedder.py": _embedder_config,
    "src/memos/embedders/universal_api.py": _universal_api_embedder,
    "src/memos/reranker/factory.py": _reranker_factory,
    "src/memos/reranker/http_bge.py": _http_bge,
    "src/memos/api/handlers/add_handler.py": _add_handler,
    "src/memos/api/config.py": _api_config,
    "src/memos/mem_scheduler/webservice_modules/rabbitmq_service.py": _rabbitmq,
}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def transformed(source: Path) -> dict[str, tuple[str, str, str]]:
    """Return relative path to preimage, transformed text and postimage digests."""

    result = {}
    for relative, transform in PATCHES.items():
        original = (source / relative).read_text()
        updated = transform(original)
        result[relative] = (_digest(original), updated, _digest(updated))
    return result


def apply_patchset(source: Path, *, verify_only: bool = False) -> None:
    """Verify the locked source and optionally write the guarded transformation."""

    results = transformed(source)
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("schema") != "memscope.memos.patchset.v1" or set(lock.get("files", {})) != set(
        PATCHES
    ):
        raise RuntimeError("patchset lock manifest is invalid")
    for relative, (pre, updated, post) in results.items():
        expected = lock["files"][relative]
        if expected != {"pre_sha256": pre, "post_sha256": post}:
            raise RuntimeError(f"patchset hash mismatch: {relative}")
        if not verify_only:
            (source / relative).write_text(updated)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--print-lock", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    results = transformed(args.source)
    if args.print_lock:
        print(
            json.dumps(
                {
                    "schema": "memscope.memos.patchset.v1",
                    "files": {
                        path: {"pre_sha256": pre, "post_sha256": post}
                        for path, (pre, _updated, post) in results.items()
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    apply_patchset(args.source, verify_only=args.verify_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
