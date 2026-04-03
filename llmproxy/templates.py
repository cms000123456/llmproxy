from __future__ import annotations

"""Prompt template engine with variable substitution."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Template:
    """A prompt template with metadata."""

    name: str
    description: str
    system_prompt: Optional[str]
    user_prompt: str
    variables: List[str]


class TemplateEngine:
    """Engine for managing and rendering prompt templates."""

    # Default built-in templates
    DEFAULT_TEMPLATES: Dict[str, Dict[str, Any]] = {
        "code_review": {
            "description": "Review code for bugs, style, and improvements",
            "system_prompt": "You are a code reviewer. Be thorough but constructive.",
            "user_prompt": """Please review the following {{ language }} code:

```{{ language }}
{{ code }}
```

Focus on:
1. Bugs and potential errors
2. Code style and best practices
3. Performance optimizations
4. Security issues

Provide specific suggestions with line references where applicable.""",
        },
        "explain_code": {
            "description": "Explain code in simple terms",
            "system_prompt": "You are a helpful programming tutor. Explain clearly and simply.",
            "user_prompt": """Please explain what this {{ language }} code does:

```{{ language }}
{{ code }}
```

Break it down step by step for a beginner.""",
        },
        "refactor": {
            "description": "Refactor code to improve quality",
            "system_prompt": "You are an expert software engineer. Improve code while maintaining functionality.",
            "user_prompt": """Please refactor the following {{ language }} code:

```{{ language }}
{{ code }}
```

Goals: {{ goals | default('improve readability and maintainability') }}

Provide the refactored code with explanations of the changes.""",
        },
        "summarize_text": {
            "description": "Summarize long text",
            "system_prompt": "You create concise, accurate summaries.",
            "user_prompt": """Please summarize the following text in {{ max_sentences | default('3') }} sentences:

{{ text }}""",
        },
        "translate": {
            "description": "Translate text between languages",
            "system_prompt": "You are a professional translator. Maintain tone and context.",
            "user_prompt": """Please translate the following text from {{ source_lang }} to {{ target_lang }}:

{{ text }}""",
        },
        "debug_error": {
            "description": "Help debug an error message",
            "system_prompt": "You are a debugging expert. Help identify root causes and solutions.",
            "user_prompt": """I'm getting the following error:

```
{{ error }}
```

Context:
- Language/Framework: {{ context | default('Not specified') }}
- Code snippet:
```
{{ code | default('Not provided') }}
```

What could be causing this and how can I fix it?""",
        },
    }

    def __init__(self, custom_templates: Optional[Dict[str, Dict[str, Any]]] = None):
        """Initialize template engine with optional custom templates."""
        self._templates: Dict[str, Template] = {}

        # Load default templates
        for name, config in self.DEFAULT_TEMPLATES.items():
            self._templates[name] = self._create_template(name, config)

        # Load custom templates (can override defaults)
        if custom_templates:
            for name, config in custom_templates.items():
                self._templates[name] = self._create_template(name, config)
                logger.info(f"Loaded custom template: {name}")

        logger.info(f"Template engine initialized with {len(self._templates)} templates")

    def _create_template(self, name: str, config: Dict[str, Any]) -> Template:
        """Create a Template object from configuration."""
        user_prompt = config.get("user_prompt", "")
        variables = self._extract_variables(user_prompt)

        # Also extract from system prompt if present
        system_prompt = config.get("system_prompt")
        if system_prompt:
            variables.extend(self._extract_variables(system_prompt))

        # Remove duplicates while preserving order
        seen: set[str] = set()
        unique_vars: list[str] = []
        for v in variables:
            if v not in seen:
                seen.add(v)
                unique_vars.append(v)

        return Template(
            name=name,
            description=config.get("description", ""),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            variables=unique_vars,
        )

    def _extract_variables(self, template: str) -> List[str]:
        """Extract variable names from a template string.

        Supports Jinja2-style syntax: {{ variable }}, {{ variable | default('value') }}
        """
        pattern = r"\{\{\s*(\w+)(?:\s*\|\s*[^}]+)?\s*\}\}"
        return re.findall(pattern, template)

    def _render_template(self, template: str, variables: Dict[str, Any]) -> str:
        """Render a template string with variable substitution.

        Supports:
        - {{ variable }} - simple substitution
        - {{ variable | default('value') }} - with default value
        """
        result = template

        # Pattern to match variables with optional default filter
        pattern = r'\{\{\s*(\w+)(?:\s*\|\s*default\([\'"]([^\'"]*)[\'"]\))?\s*\}\}'

        for match in re.finditer(pattern, template):
            full_match = match.group(0)
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else ""

            value = variables.get(var_name, default_value)
            result = result.replace(full_match, str(value))

        return result

    def render(self, template_name: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Render a template to a chat completion request format.

        Returns:
            Dict with 'messages' key formatted for chat completions API
        """
        if template_name not in self._templates:
            raise TemplateNotFoundError(f"Template '{template_name}' not found")

        template = self._templates[template_name]
        messages = []

        # Add system message if present
        if template.system_prompt:
            rendered_system = self._render_template(template.system_prompt, variables)
            messages.append({"role": "system", "content": rendered_system})

        # Add user message
        rendered_user = self._render_template(template.user_prompt, variables)
        messages.append({"role": "user", "content": rendered_user})

        logger.debug(
            f"Rendered template '{template_name}' with variables: {list(variables.keys())}"
        )

        return {"messages": messages}

    def list_templates(self) -> Dict[str, Dict[str, Any]]:
        """List all available templates with their metadata."""
        return {
            name: {"description": t.description, "variables": t.variables}
            for name, t in self._templates.items()
        }

    def get_template(self, name: str) -> Optional[Template]:
        """Get a specific template by name."""
        return self._templates.get(name)

    def validate_variables(self, template_name: str, variables: Dict[str, Any]) -> List[str]:
        """Validate that all required variables are provided.

        Returns list of missing required variables (those without defaults).
        """
        template = self._templates.get(template_name)
        if not template:
            return []

        # For now, all variables are considered optional if they have defaults
        # Variables without defaults are required
        template_str = template.user_prompt
        if template.system_prompt:
            template_str += template.system_prompt

        # Find all variables and check if they have defaults
        pattern = r'\{\{\s*(\w+)(?:\s*\|\s*default\([\'"]([^\'"]*)[\'"]\))?\s*\}\}'
        matches = re.finditer(pattern, template_str)

        missing = []
        for match in matches:
            var_name = match.group(1)
            has_default = match.group(2) is not None

            if var_name not in variables and not has_default:
                missing.append(var_name)

        return missing


class TemplateNotFoundError(Exception):
    """Raised when a requested template is not found."""

    pass


# Global template engine instance
_template_engine: Optional[TemplateEngine] = None


def init_template_engine(custom_templates: Optional[Dict[str, Dict[str, Any]]] = None) -> TemplateEngine:
    """Initialize the global template engine."""
    global _template_engine
    _template_engine = TemplateEngine(custom_templates)
    return _template_engine


def get_template_engine() -> TemplateEngine:
    """Get the global template engine instance."""
    if _template_engine is None:
        return init_template_engine()
    return _template_engine
