"""CV Extractor Agent using OpenAI Agent SDK."""

from pathlib import Path
from typing import Dict, Any
from agents import RunContextWrapper, Agent, ModelSettings, TResponseInputItem, Runner, RunConfig
from openai.types.shared.reasoning import Reasoning
from pydantic import BaseModel
from loguru import logger
from config.agent_config import DEFAULT_AGENT_CONFIG

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "cv_extractor.md"
PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")


class ExtractContext:
    """Context for the extraction workflow."""
    
    def __init__(self, workflow_input_as_text: str):
        self.workflow_input_as_text = workflow_input_as_text


class WorkflowInput(BaseModel):
    """Input model for the workflow."""
    
    input_as_text: str


def extract_instructions(
    run_context: RunContextWrapper[ExtractContext], 
    _agent: Agent[ExtractContext]
) -> str:
    """Generate instructions for the CV extraction agent."""
    workflow_input_as_text = run_context.context.workflow_input_as_text
    return f"{PROMPT_TEMPLATE}\n{workflow_input_as_text}"


class CVExtractorAgent:
    """Wrapper for the OpenAI CV Extraction Agent."""
    
    def __init__(self, config=None):
        """
        Initialize the CV Extractor Agent.
        
        Args:
            config: Agent configuration (uses DEFAULT_AGENT_CONFIG if None)
        """
        self.config = config or DEFAULT_AGENT_CONFIG
        self.agent = Agent(
            name="Extract",
            instructions=extract_instructions,
            model=self.config.model,
            model_settings=ModelSettings(
                store=self.config.store_conversations,
                reasoning=Reasoning(effort=self.config.reasoning_effort)
            )
        )
        logger.info(f"Initialized CV Extractor Agent with model: {self.config.model}")
    
    async def extract_cv_info(self, cv_text: str) -> Dict[str, Any]:
        """
        Extract information from CV text using the OpenAI Agent.
        
        Args:
            cv_text: The text content of the CV
            
        Returns:
            Dictionary containing extracted information
            
        Raises:
            Exception: If extraction fails
        """
        try:
            logger.info("Starting CV extraction...")
            
            # Prepare workflow input
            workflow_input = WorkflowInput(input_as_text=cv_text)
            workflow = workflow_input.model_dump()
            
            # Prepare conversation history
            conversation_history: list[TResponseInputItem] = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": workflow["input_as_text"]
                        }
                    ]
                }
            ]
            
            # Run the agent
            extract_result_temp = await Runner.run(
                self.agent,
                input=[*conversation_history],
                run_config=RunConfig(
                    trace_metadata={
                        "__trace_source__": "agent-builder",
                        "workflow_id": self.config.workflow_id
                    }
                ),
                context=ExtractContext(workflow_input_as_text=workflow["input_as_text"])
            )
            
            # Extract output
            extract_result = {
                "output_text": extract_result_temp.final_output_as(str),
                "status": "success"
            }
            
            logger.info("CV extraction completed successfully")
            return extract_result
            
        except Exception as e:
            logger.error(f"Error during CV extraction: {str(e)}")
            return {
                "output_text": None,
                "status": "error",
                "error_message": str(e)
            }
    
    async def run_workflow(self, workflow_input: WorkflowInput) -> Dict[str, Any]:
        """
        Run the complete workflow for CV extraction.
        
        Args:
            workflow_input: WorkflowInput object containing the CV text
            
        Returns:
            Dictionary containing extraction results
        """
        return await self.extract_cv_info(workflow_input.input_as_text)
