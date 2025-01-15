"""Video analysis prompt templates."""


ANALYSIS_PROMPT_TEMPLATE = """Analyze this video and provide recommendations for potential improvements.

## Video Information
{video_metadata}

## Analysis Tasks
1. Identify any technical issues (resolution, encoding, audio levels)
2. Suggest potential enhancements based on content type
3. Note any optimization opportunities (file size, format)

## Response Format
Provide a structured analysis:
```json
{{
  "technical_assessment": {{
    "resolution_quality": "good/fair/poor",
    "encoding_efficiency": "good/fair/poor",
    "audio_quality": "good/fair/poor"
  }},
  "suggested_improvements": [
    {{"skill": "skill_name", "reason": "why this would help"}}
  ],
  "optimization_notes": "any size/format recommendations"
}}
```
"""


def get_analysis_prompt(video_metadata: str) -> str:
    """Generate an analysis prompt for a video.

    Args:
        video_metadata: Video metadata string from analyzer.

    Returns:
        Formatted analysis prompt.
    """
    return ANALYSIS_PROMPT_TEMPLATE.format(video_metadata=video_metadata)


COMPLEXITY_ANALYSIS_PROMPT = """Analyze this editing request and estimate its complexity.

## User Request
"{user_request}"

## Available Skills
{available_skills}

## Analysis Required
1. List the skills likely needed
2. Estimate processing complexity (light/medium/heavy)
3. Identify any potential conflicts or issues

## Response Format
```json
{{
  "required_skills": ["skill1", "skill2"],
  "complexity": "light|medium|heavy",
  "conflicts": ["any skill conflicts"],
  "preprocessing_needed": true/false,
  "notes": "additional observations"
}}
```
"""


def get_complexity_prompt(user_request: str, skills_list: str) -> str:
    """Generate a complexity analysis prompt.

    Args:
        user_request: The user's editing request.
        skills_list: String listing available skills.

    Returns:
        Formatted complexity analysis prompt.
    """
    return COMPLEXITY_ANALYSIS_PROMPT.format(
        user_request=user_request,
        available_skills=skills_list,
    )
