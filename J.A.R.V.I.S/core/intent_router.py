import asyncio
import datetime
import logging
import re
import platform
from core.listener import JarvisInterface
from core.llm_client import brain
from core.speech_output import speaker
from core.semantic_router import SemanticRouter

from core.security_filter import security_filter
from core.voice_authenticator import voice_auth
from skills.engineer_skill import engineer_skill
from memory.cognee_bridge import memory
from integrations.hermes_submind import hermes_submind, HermesTaskResult
from skills.system_explorer import system_explorer
from skills.notifier_skill import notifier
from core.face_module import FaceModule
from core.prompt_refiner import refiner

logger = logging.getLogger("jarvis.router")

class IntentRouter:
    """
    Asynchronous Intent Router.
    Routes user speech to either specific local tools or the LLM brain.
    Now uses Semantic Routing + Role-Based Access Control (Host vs Guest).
    """
    # Intents blocked in Guest mode
    HOST_ONLY_INTENTS = {"TERMINAL_COMMAND", "SHUTDOWN", "SYSTEM_STATUS", "PROJECT_ANALYSIS"}
    
    # Intents requiring Human-in-the-Loop approval / Biometric Verification
    SENSITIVE_INTENTS = {"TERMINAL_COMMAND", "SHUTDOWN", "FILE_MODIFICATION", "PERMISSION_CHANGE", "ENROLL_VOICE", "CODE_MODIFICATION", "DEBUG_SYSTEM", "MULTI_STEP_TASK", "SYSTEM_OPTIMIZATION", "DEEP_SYNC", "MEMORY_IMPROVEMENT", "PROJECT_ANALYSIS"}
    VALID_INTENTS = {
        "GET_WEATHER", "PLAY_YOUTUBE", "GET_NEWS", "WEB_SEARCH",
        "SYSTEM_STATUS", "TERMINAL_COMMAND", "SHUTDOWN", "ENROLL_VOICE",
        "IDENTIFY_ME", "CODE_MODIFICATION", "DEBUG_SYSTEM",
        "MULTI_STEP_TASK", "SYSTEM_OPTIMIZATION", "DEEP_SYNC",
        "MEMORY_IMPROVEMENT", "KNOWLEDGE_REQUEST", "CONVERSATION", "PROJECT_ANALYSIS"
    }

    def __init__(self, interface: JarvisInterface, session, host_mode: bool = True):
        self.interface = interface
        self.session = session
        self.brain = brain
        self.semantic_router = SemanticRouter()
        self._initialized = False
        self.host_mode = host_mode  # True = full access, False = read-only guest
        self.face_module = FaceModule()
        self.AUTH_EXPIRY_SECONDS = 600 # 10 minutes

    async def _ensure_initialized(self):
        if not self._initialized:
            await self.semantic_router.initialize()
            self._initialized = True

    async def on_project_audit_complete(self, result: HermesTaskResult):
        """Callback when Hermes finishes a project audit."""
        logger.info(f"[CALLBACK] Project Audit: {result.status}")
        if result.status == "success":
            await speaker.speak("Sir, Hermes has completed the project architecture audit. I have found several points for optimization.")
            await notifier.notify("🤖 Hermes Project Audit", f"Audit complete. Findings: {result.result_text[:300]}...")
            
            # Record as a formal cognitive milestone
            await memory.record_reflection(
                task="Deep Architecture Audit (Hermes)",
                outcome="Audit Success",
                reflection=f"Hermes performed a deep audit. Result: {result.result_text}"
            )
        else:
            await speaker.speak("I'm sorry Sir, but the Hermes project audit encountered a technical interruption.")

    async def process_command(self, text: str, audio_path: str = None, forced_intent: str = None):
        """
        Main entry point for command processing.
        Routes to fast-path tools, semantic skills, or the LLM brain.
        """
        if not text:
            return

        text_clean = text.lower().strip()
        await self._ensure_initialized()
        
        # 1. Ultra-Fast Path: Literal/Simple Regex (Zero latency)
        # We use word-boundary checks to avoid matching "update" for "date"
        words = text_clean.split()
        if any(w in words for w in ["time", "clock"]) or "what time" in text_clean:
            now = datetime.datetime.now()
            await speaker.speak(f"The current time is {now.strftime('%I:%M %p')}, Sir.")
            return

        if any(w in words for w in ["date", "today"]) or "what day" in text_clean:
            now = datetime.datetime.now()
            await speaker.speak(f"Today is {now.strftime('%A, %B %d, %Y')}, Sir.")
            return

        if any(w in text_clean for w in ["stop music", "shut up jarvis", "stop playing", "stop the song"]):
            from skills.youtube_skill import stop_music
            await speaker.speak("Stopping music playback, Sir.")
            stop_music()
            return

        # [FAST-PATH] Engineering & Debugging & Voice Enrollment
        if any(w in text_clean for w in ["debug", "fix code", "modify code", "edit code", "help me debug"]):
            await speaker.speak("Initiating engineering diagnostic sequence, Sir. Accessing internal systems.")
            await engineer_skill.execute(text_clean)
            await memory.record_reflection("Engineering Diagnostic", "Initiated code analysis/fix", f"User requested debugging for: {text_clean}")
            return
            
        if any(w in text_clean for w in ["enroll my voice", "start voice enrollment", "enroll voice", "and roll", "unroll", "enroll"]):
            from skills.voice_enroll_skill import enroll_voice_routine
            await enroll_voice_routine(self.interface)
            return

        if any(w in text_clean for w in ["rebuild memory", "rebuild my memory", "rebuild knowledge", "reindex memory", "cognify"]):
            await speaker.speak("Initiating manual knowledge graph rebuild, Sir. This may take several minutes depending on Ollama's load.")
            result = await memory.force_cognify()
            await speaker.speak(result)
            return

        # 2. Semantic Routing (The Intelligence Layer)
        normalized_forced = (forced_intent or "").strip().upper()
        if normalized_forced and normalized_forced in self.VALID_INTENTS and normalized_forced != "KNOWLEDGE_REQUEST":
            intent, score = normalized_forced, 1.0
            logger.info(f"Using neurally refined intent: {intent}")
        else:
            intent, score = await self.semantic_router.route(text_clean)
        
        # [OPTIMIZATION] Neural Command Cleaning via Gemini Flash
        # Only clean if confidence is genuinely low or command is complex
        if score < 0.65 or len(text_clean.split()) > 5:
            logger.info(f"Triggering Gemini Flash Refinement (Confidence: {score:.2f})...")
            refined_data = await refiner.refine(text)
            if refined_data and refined_data.get("refined_text") and refined_data.get("confidence") > 0.4:
                logger.info(f"Gemini Refined: '{text_clean}' -> '{refined_data['refined_text']}' [Intent: {refined_data['intent']}]")
                text_clean = refined_data["refined_text"].lower()
                intent = refined_data["intent"]
                score = refined_data["confidence"]

        # Role-Based Access Control: block host-only intents for guests
        if not self.host_mode and intent in self.HOST_ONLY_INTENTS:
            logger.warning(f"Guest attempted host-only intent: {intent}")
            await speaker.speak("I apologize, but that action requires Host authorization. Please ensure the host is present.")
            return

        # 3. Multimodal Biometric Authentication Gatekeeper
        if intent in self.SENSITIVE_INTENTS:
            logger.info(f"Sensitive intent detected: {intent}. Checking authentication status...")
            
            # [PHASE 1] Session-based bypass
            now = datetime.datetime.now()
            
            is_authenticated = False
            if self.session.last_verified_time:
                seconds_since_auth = (now - self.session.last_verified_time).total_seconds()
                if seconds_since_auth < self.AUTH_EXPIRY_SECONDS:
                    logger.info(f"Using persisted authentication ({self.session.auth_method}, {seconds_since_auth:.1f}s ago).")
                    is_authenticated = True
            
            if not is_authenticated:
                logger.info("No valid session authentication. Initiating Multimodal Fallback...")
                
                # [PHASE 2] Voice Verification
                voice_verified = False
                if audio_path:
                    if voice_auth.verify(audio_path):
                        voice_verified = True
                        self.session.auth_method = "voice"
                        logger.info("Voice identity verified.")
                    else:
                        logger.warning("Voice verification failed. Falling back to Face-ID...")
                
                # [PHASE 3] Multimodal Fallback: Face-ID
                face_verified = False
                if not voice_verified:
                    def _silent_face_scan():
                        if self.face_module.initialize():
                            return self.face_module.verify(tolerance=0.62)
                        return None
                    
                    loop = asyncio.get_running_loop()
                    face_result = await loop.run_in_executor(None, _silent_face_scan)
                    
                    if face_result and face_result.get("name") not in ("unknown", "no_face", "no_encoding", "error"):
                        face_verified = True
                        self.session.auth_method = "face"
                        logger.info(f"Face identity verified: {face_result['name']}")
                
                if voice_verified or face_verified:
                    is_authenticated = True
                    self.session.last_verified_time = now
                    self.session.verified_user = face_result['name'] if face_verified else "Rudrapratap"
                    self.host_mode = True
                else:
                    logger.warning("ALL BIOMETRIC CHECKS FAILED. Unauthorized access attempt.")
                    from skills.notifier_skill import notifier
                    await notifier.notify(
                        title="⚠️ SECURITY ALERT: Biometric Verification Failed",
                        message=(
                            f"Sir, an unauthorized user attempted to execute a sensitive command.\n\n"
                            f"INTENT: {intent}\n"
                            f"COMMAND: {text_clean}\n"
                            f"STATUS: Access Denied via Multimodal Neural Gate."
                        ),
                        priority="high"
                    )
                    await speaker.speak("Identity not verified. Biometric fallback failed. Access denied.")
                    return
        
        # [NEW] Hermes Delegation Check
        if await self.should_delegate_to_hermes(intent, text_clean, score):
            if await self.delegate_to_hermes(text, intent, audio_path):
                return # Handled by Hermes
        
        if intent == "GET_WEATHER":
            # Extract city if mentioned
            city = "Mumbai" # Default
            match = re.search(r"in ([\w\s]+)", text_clean)
            if match:
                city = match.group(1).strip()
            
            from skills.weather_news_skill import weather_news
            report = weather_news.get_weather(city)
            await speaker.speak(report)
            return

        elif intent == "PLAY_YOUTUBE":
            song_query = text_clean.replace("youtube", "").replace("play", "").strip()
            if not song_query:
                await speaker.speak("What should I play for you on YouTube, Sir?")
                return
            from skills.youtube_skill import play_video
            await speaker.speak(f"Searching YouTube for {song_query}, Sir.")
            # Run in executor because play_video can be slow (network search)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, play_video, song_query)
            return

        elif intent == "ENROLL_VOICE":
            from skills.voice_enroll_skill import enroll_voice_routine
            await enroll_voice_routine(self.interface)
            return

        elif intent == "SYSTEM_STATUS":
            from skills.dynamic_monitor import monitor
            report = await monitor.generate_health_report()
            await speaker.speak(report)
            return
            
        elif intent == "IDENTIFY_ME":
            if not audio_path:
                await speaker.speak("I heard your request, Sir, but I don't have enough audio data to verify your identity.")
                return
            
            await speaker.speak("Processing biometric signature. One moment.")
            
            # Step 1: Voice Auth
            voice_verified = voice_auth.verify(audio_path)
            
            # Step 2: Face-ID Fallback if Voice fails
            face_verified = False
            verified_name = "Guest"
            
            if not voice_verified:
                logger.warning("Voice signature match low. Activating Face-ID fallback...")
                def _scan():
                    if self.face_module.initialize():
                        return self.face_module.verify(tolerance=0.62)
                    return None
                
                loop = asyncio.get_running_loop()
                face_result = await loop.run_in_executor(None, _scan)
                
                if face_result and face_result.get("name") not in ("unknown", "no_face", "no_encoding", "error"):
                    face_verified = True
                    verified_name = face_result['name']
                    logger.info(f"Face-ID Fallback successful: {verified_name}")

            if voice_verified or face_verified:
                user_name = verified_name if face_verified else "Rudrapratap"
                await speaker.speak(f"Biometric signature confirmed. You are recognized as {user_name}. Host access granted.")
                self.host_mode = True
                self.session.verified_user = user_name
                self.session.last_verified_time = datetime.datetime.now()
                self.session.auth_method = "face" if face_verified else "voice"
            else:
                await speaker.speak("I could not confirm your identity via vocal signature or facial recognition. You are currently operating in Guest Mode.")
                self.host_mode = False
            return

        elif intent == "GET_NEWS":
            from skills.weather_news_skill import weather_news
            report = weather_news.get_news()
            await speaker.speak(report)
            return

        elif intent == "WEB_SEARCH":
            search_query = text_clean.replace("search", "").replace("google", "").replace("for", "").strip()
            if search_query:
                from skills.gemini_skill import gemini_core
                await speaker.speak(f"Accessing satellite data for {search_query}...")
                response = await gemini_core.ask(search_query)
                await speaker.speak(response)
                return

        elif intent == "DEEP_SYNC":
            try:
                await speaker.speak("Initiating Full Neural Sync. I am crawling all workspace projects and ingesting their logic into our knowledge graph. This may take a moment, Sir.")
                result = await system_explorer.sync_workspace_to_memory()
                logger.info(f"Neural Sync result: {result}")
                await speaker.speak("Neural Sync complete. My knowledge graph has been updated with the latest workspace structure.")
            except Exception as e:
                logger.error(f"DEEP_SYNC failed: {e}", exc_info=True)
                await speaker.speak("I apologize Sir, my neural indexing encountered a synchronization error. I am maintaining core functionality in degraded mode.")
            return

        elif intent == "MEMORY_IMPROVEMENT":
            try:
                await speaker.speak("Sir, I am now consolidating our knowledge graph and rebuilding the neural index. This involves deep cognee processing.")
                result = await memory.force_cognify()
                await speaker.speak(result)
                await memory.record_reflection(
                    task="Manual Memory Graph Rebuild",
                    outcome=result,
                    reflection="Manually triggered a full Cognify process to consolidate the knowledge graph and resolve empty search results."
                )
            except Exception as e:
                logger.error(f"MEMORY_IMPROVEMENT failed: {e}", exc_info=True)
                await speaker.speak("I apologize Sir, my neural indexing encountered a synchronization error. I am maintaining core functionality in degraded mode.")
            return

        elif intent == "TERMINAL_COMMAND":
            await speaker.speak("Sir, you are requesting terminal access. This is a high-level operation.")
            if await self._request_approval("Authorize terminal access?"):
                from core.face_module import FaceModule
                fm = FaceModule()
                await speaker.speak("Initiating biometric scan for final verification.")
                
                def _guard_scan():
                    if fm.initialize():
                        return fm.guard_mode()
                    return False
                
                loop = asyncio.get_running_loop()
                verified = await loop.run_in_executor(None, _guard_scan)
                
                if verified:
                    await speaker.speak("Identity confirmed. Terminal is ready for your instructions.")
                    await memory.record_reflection(
                        task="Terminal Access Granted",
                        outcome="User entered terminal guard mode",
                        reflection="Authorized terminal access after successful biometric verification. Standing by for high-level commands."
                    )
                else:
                    await speaker.speak("Verification failed. Terminal access denied.")
            else:
                await speaker.speak("Operation cancelled. Safety protocol maintained.")
            return

        elif intent == "SHUTDOWN":
            if await self._request_approval("Confirm system deactivation?"):
                await memory.record_reflection(
                    task="System Shutdown",
                    outcome="Terminating all processes",
                    reflection="User initiated a full system shutdown. Closing all neural connections."
                )
                await speaker.speak("Deactivating systems. Goodbye, Sir.")
                exit(0)
            else:
                await speaker.speak("Shutdown aborted.")
            return

        elif intent in ["CODE_MODIFICATION", "DEBUG_SYSTEM"]:
            # These are high-level engineering tasks
            await speaker.speak(f"Sir, you are requesting a {intent.lower().replace('_', ' ')}. This will modify my internal systems.")
            if await self._request_approval(f"Authorize {intent.lower().replace('_', ' ')}?"):
                await engineer_skill.execute(text_clean)
                await memory.record_reflection(
                    task=f"System Change: {intent}", 
                    outcome="Executed engineering skill", 
                    reflection=f"Modified internal code via {intent}. User command: '{text_clean}'."
                )
            else:
                await speaker.speak("Engineering sequence aborted, Sir.")
        elif intent == "PROJECT_ANALYSIS":
            await speaker.speak("Initiating comprehensive project analysis, Sir. I will scan the codebase and evaluate the architecture.")
            if await self._request_approval("Authorize project-wide diagnostic?"):
                # 1. First sync to memory so we have fresh context
                await speaker.speak("Synchronizing workspace architecture with my neural graph...")
                summary = await system_explorer.sync_workspace_to_memory()
                
                # 2. Check if we should delegate to Hermes for deep analysis
                if any(word in text_clean for word in ["change", "fix", "bug", "improve", "refactor", "evaluate"]):
                    await speaker.speak("Workspace sync complete. Sir, since you mentioned analyzing for changes, shall I delegate a deep diagnostic to the Hermes Submind?")
                    if await self._request_approval("Authorize Hermes deep scan?"):
                        await speaker.speak("Hermes is now performing a deep architecture audit. I will notify you of any structural recommendations.")
                        await hermes_submind.queue_hermes_task(
                            description=f"Perform a deep architecture audit of the J.A.R.V.I.S. project. Focus on: {text_clean}. Suggest 3 major improvements.",
                            toolsets=["terminal", "file"],
                            on_complete_callback=self.on_project_audit_complete
                        )
                else:
                    # SENTIENT REFLECTION: Ask the brain to comment on the summary
                    reflection = await self.brain.chat(f"I have just completed a full workspace sync. The summary is: {summary}. Give a concise, JARVIS-like reflection on this state.")
                    await speaker.speak(reflection)
                
                # Record as a formal cognitive milestone
                await memory.record_reflection(
                    task="Full Workspace Analysis & Neural Sync",
                    outcome=summary,
                    reflection=f"Performed a deep scan of the J.A.R.V.I.S. workspace. {summary}. Architecture knowledge is now synchronized."
                )
            return

        # 3. Slow-Path: General Conversation (Ollama/Claw)
        now = datetime.datetime.now()
        context = {
            "current_time": now.strftime("%I:%M %p"),
            "current_date": now.strftime("%B %d, %Y"),
            "user_name": "Rudrapratap",
            "platform": f"{platform.system()} {platform.release()}",
            "system_load": "optimal"
        }
        
        enhanced_query = f"[Context: {context}] {text}"
        # [SECURITY] Check for sensitive keywords in general conversation
        if security_filter.is_sensitive_command(text):
            logger.warning(f"Sensitive command detected in chat: {text}")
            if not await self._request_approval(f"Authorization required for sensitive request: {text_clean}"):
                await speaker.speak("I am sorry Sir, but I cannot fulfill that request without your explicit authorization.")
                return

        try:
            # Increased timeouts for complex analysis tasks
            timeout = 180.0 if self.brain.use_claw else 120.0
            response = await asyncio.wait_for(self.brain.chat(enhanced_query), timeout=timeout)
            
            if response:
                await speaker.speak(response)
            else:
                await speaker.speak("I processed your request, Sir, but I'm afraid I don't have a definitive answer at the moment.")
                
        except asyncio.TimeoutError:
            from integrations.hermes_submind import hermes_submind
            if hermes_submind and hermes_submind.hermes_ready:
                await speaker.speak("Sir, this request is requiring extensive neural processing. I am moving it to my Hermes submind for background completion so I can remain available.")
                await hermes_submind.queue_hermes_task(
                    description=f"Complete the user's request: {text_clean}. Context: {context}",
                    priority="high"
                )
            else:
                await speaker.speak("I'm sorry Sir, my neural core is taking longer than expected and my submind is unavailable. Please try again.")
        except Exception as e:
            logger.error(f"Router processing failed: {e}")
            await speaker.speak("Sir, I am experiencing a temporary disconnect from my processing core.")

    async def _request_approval(self, prompt: str) -> bool:
        """Request biometric or verbal approval for sensitive actions."""
        await speaker.speak(f"{prompt}. I am verifying your identity.")
        
        # [PHASE 1] Silent Face-ID Check (Iron Man style)
        logger.info("Attempting silent Face-ID authorization...")
        def _silent_scan():
            if self.face_module.initialize():
                return self.face_module.verify(tolerance=0.6)
            return None
        
        loop = asyncio.get_running_loop()
        face_result = await loop.run_in_executor(None, _silent_scan)
        
        if face_result and face_result.get("name") not in ("unknown", "no_face", "no_encoding", "error"):
            logger.info(f"Face-ID Authorization Successful: {face_result['name']}")
            await speaker.speak("Biometric signature confirmed. Access granted.")
            return True

        # [PHASE 2] Verbal Fallback if Face fails
        await speaker.speak("Please say 'Authorize' or 'Proceed' to confirm verbally.")
        
        # Wrapped in executor to avoid blocking the event loop
        text_result = await loop.run_in_executor(None, self.interface.listen)
        
        if text_result:
            response = text_result[0] if isinstance(text_result, tuple) else text_result
            if response and any(w in response.lower() for w in ["authorize", "proceed", "yes", "do it"]):
                logger.info("User AUTHORIZED sensitive action via voice.")
                return True
        
        logger.warning("User DENIED or TIMED OUT sensitive action.")
        return False

    async def _neural_clean(self, noisy_text: str) -> str:
        """Use local LLM to strip noise from voice commands."""
        prompt = (
            "You are the Neural Command Cleaner for J.A.R.V.I.S. "
            "Your task is to take a noisy voice-to-text transcript and return ONLY a clean, "
            "direct system command. Strip away filler words, repeated wake words, or honorifics.\n\n"
            "Examples:\n"
            "'Jarvis Sir J.A.R.V.I.S., sunflower on YouTube.' -> 'play sunflower on youtube'\n"
            "'Hey Jarvis tell me what is the time right now' -> 'what is the time'\n"
            "'Jarvis play some music from metro boomin' -> 'play metro boomin'\n\n"
            f"Noisy Text: '{noisy_text}'\n"
            "Clean Command:"
        )
        try:
            # Use a faster, shorter response for cleaning
            response = await self.brain.chat(prompt)
            if response:
                # Clean up any quotes or extra text the LLM might add
                cleaned = response.strip().lower().replace("'", "").replace("\"", "")
                return cleaned
        except Exception as e:
            logger.error(f"Neural clean failed: {e}")
        return None

    async def should_delegate_to_hermes(self, intent: str, text: str, score: float) -> bool:
        """Decide if a command should be delegated to Hermes."""
        if not hermes_submind or not hermes_submind.hermes_ready:
            return False
        
        # Complex or multi-step intents
        complex_intents = {"CODE_ANALYSIS", "RESEARCH", "MULTI_STEP_TASK", "SYSTEM_OPTIMIZATION"}
        if intent in complex_intents:
            return True
            
        # Large requests with low confidence are good for Hermes
        if len(text.split()) > 10 and score < 0.8:
            return True
            
        return False

    async def delegate_to_hermes(self, text: str, intent: str, audio_path: str = None) -> bool:
        """Delegate command to Hermes submind."""
        if not hermes_submind:
            return False
            
        try:
            logger.info(f"[ROUTER\u2192HERMES] Delegating: {text[:60]}")
            result = await hermes_submind.call_hermes(
                description=text,
                context={"user_command": True, "intent": intent},
                toolsets=self._infer_toolsets(text)
            )
            
            if result.status == "success" and result.result_text:
                await speaker.speak(self._cleanup_for_speech(result.result_text))
                return True
            return False
        except Exception as e:
            logger.error(f"Hermes delegation failed: {e}")
            return False

    def _infer_toolsets(self, text: str) -> list:
        toolsets = []
        t = text.lower()
        if any(w in t for w in ["run", "execute", "command", "test"]): toolsets.append("terminal")
        if any(w in t for w in ["file", "create", "write"]): toolsets.append("file")
        if any(w in t for w in ["search", "find", "web"]): toolsets.append("web")
        if any(w in t for w in ["browse", "visit"]): toolsets.append("browser")
        return toolsets if toolsets else ["terminal", "file", "web"]
