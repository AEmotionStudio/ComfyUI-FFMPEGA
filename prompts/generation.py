"""Pipeline generation prompt templates."""


GENERATION_PROMPT_TEMPLATE = """Generate an FFMPEG processing pipeline for this request.

## User Request
"{user_request}"

## Input Video
{video_metadata}

## Instructions
Create a precise pipeline using only available skills. Output valid JSON.

## Response Format
```json
{{
  "interpretation": "your understanding of the request",
  "pipeline": [
    {{"skill": "skill_name", "params": {{...}}}}
  ],
  "warnings": [],
  "estimated_changes": "description of output changes"
}}
```
"""


def get_generation_prompt(user_request: str, video_metadata: str) -> str:
    """Generate a pipeline generation prompt.

    Args:
        user_request: The user's editing request.
        video_metadata: Video metadata string.

    Returns:
        Formatted generation prompt.
    """
    return GENERATION_PROMPT_TEMPLATE.format(
        user_request=user_request,
        video_metadata=video_metadata,
    )


REFINEMENT_PROMPT_TEMPLATE = """Refine this pipeline based on user feedback.

## Original Request
"{original_request}"

## Current Pipeline
{current_pipeline}

## User Feedback
"{feedback}"

## Instructions
Modify the pipeline according to the feedback while preserving working parts.
Only change what the feedback specifically addresses.

## Response Format
```json
{{
  "interpretation": "how you interpreted the feedback",
  "pipeline": [
    {{"skill": "skill_name", "params": {{...}}}}
  ],
  "changes_made": ["list of changes from original"],
  "warnings": []
}}
```
"""


def get_refinement_prompt(
    original_request: str,
    current_pipeline: str,
    feedback: str,
) -> str:
    """Generate a pipeline refinement prompt.

    Args:
        original_request: The original editing request.
        current_pipeline: JSON string of current pipeline.
        feedback: User's feedback for refinement.

    Returns:
        Formatted refinement prompt.
    """
    return REFINEMENT_PROMPT_TEMPLATE.format(
        original_request=original_request,
        current_pipeline=current_pipeline,
        feedback=feedback,
    )


BATCH_PROMPT_TEMPLATE = """Generate a pipeline for batch processing multiple videos.

## User Request
"{user_request}"

## Sample Video Info
{sample_video_metadata}

## Batch Details
- Number of videos: {video_count}
- File pattern: {file_pattern}

## Instructions
Create a pipeline that will work consistently across all videos.
Use relative/percentage values where possible for better compatibility.

## Response Format
```json
{{
  "interpretation": "understanding of batch request",
  "pipeline": [
    {{"skill": "skill_name", "params": {{...}}}}
  ],
  "batch_notes": "considerations for batch processing",
  "warnings": []
}}
```
"""


def get_batch_prompt(
    user_request: str,
    sample_metadata: str,
    video_count: int,
    file_pattern: str,
) -> str:
    """Generate a batch processing prompt.

    Args:
        user_request: The user's editing request.
        sample_metadata: Metadata from a sample video.
        video_count: Number of videos in batch.
        file_pattern: File glob pattern.

    Returns:
        Formatted batch processing prompt.
    """
    return BATCH_PROMPT_TEMPLATE.format(
        user_request=user_request,
        sample_video_metadata=sample_metadata,
        video_count=video_count,
        file_pattern=file_pattern,
    )
