"""Tests for prompt template engine."""

import pytest
from llmproxy.templates import (
    Template, TemplateEngine, TemplateNotFoundError,
    init_template_engine, get_template_engine
)


class TestTemplate:
    """Tests for the Template dataclass."""

    def test_template_creation(self):
        """Test creating a Template object."""
        template = Template(
            name="test",
            description="A test template",
            system_prompt="You are a tester.",
            user_prompt="Test {{ variable }}",
            variables=["variable"]
        )
        
        assert template.name == "test"
        assert template.description == "A test template"
        assert template.system_prompt == "You are a tester."
        assert template.user_prompt == "Test {{ variable }}"
        assert template.variables == ["variable"]

    def test_template_optional_system_prompt(self):
        """Test that system_prompt can be None."""
        template = Template(
            name="test",
            description="A test template",
            system_prompt=None,
            user_prompt="Test {{ variable }}",
            variables=["variable"]
        )
        
        assert template.system_prompt is None


class TestTemplateEngine:
    """Tests for the TemplateEngine class."""

    def test_default_templates_loaded(self):
        """Test that default templates are loaded on initialization."""
        engine = TemplateEngine()
        
        # Check that built-in templates exist
        assert "code_review" in engine.list_templates()
        assert "explain_code" in engine.list_templates()
        assert "refactor" in engine.list_templates()
        assert "summarize_text" in engine.list_templates()
        assert "translate" in engine.list_templates()
        assert "debug_error" in engine.list_templates()

    def test_custom_templates_override_defaults(self):
        """Test that custom templates can override defaults."""
        custom = {
            "code_review": {
                "description": "Custom code review",
                "system_prompt": "Custom system prompt",
                "user_prompt": "Review this: {{ code }}",
            }
        }
        engine = TemplateEngine(custom)
        
        template = engine.get_template("code_review")
        assert template.description == "Custom code review"
        assert template.system_prompt == "Custom system prompt"

    def test_custom_templates_added(self):
        """Test that custom templates are added alongside defaults."""
        custom = {
            "my_template": {
                "description": "My custom template",
                "user_prompt": "Do {{ action }}",
            }
        }
        engine = TemplateEngine(custom)
        
        # Custom template exists
        assert "my_template" in engine.list_templates()
        
        # Default templates still exist
        assert "code_review" in engine.list_templates()

    def test_extract_variables(self):
        """Test variable extraction from template strings."""
        engine = TemplateEngine()
        
        variables = engine._extract_variables("Hello {{ name }}, you are {{ age }} years old.")
        assert "name" in variables
        assert "age" in variables

    def test_render_template_simple(self):
        """Test rendering a template with simple variables."""
        engine = TemplateEngine()
        
        result = engine.render("code_review", {
            "language": "python",
            "code": "def test(): pass"
        })
        
        assert "messages" in result
        assert len(result["messages"]) == 2  # system + user
        assert result["messages"][0]["role"] == "system"
        assert result["messages"][1]["role"] == "user"
        assert "python" in result["messages"][1]["content"]
        assert "def test(): pass" in result["messages"][1]["content"]

    def test_render_template_with_default(self):
        """Test rendering with default values."""
        engine = TemplateEngine()
        
        # summarize_text has default max_sentences=3
        result = engine.render("summarize_text", {
            "text": "Some long text here."
        })
        
        assert "3" in result["messages"][1]["content"]

    def test_render_template_multiple_variables(self):
        """Test rendering with multiple variables."""
        engine = TemplateEngine()
        
        result = engine.render("translate", {
            "source_lang": "English",
            "target_lang": "Spanish",
            "text": "Hello world"
        })
        
        content = result["messages"][1]["content"]
        assert "English" in content
        assert "Spanish" in content
        assert "Hello world" in content

    def test_render_code_review_template(self):
        """Test the code_review template specifically."""
        engine = TemplateEngine()
        
        result = engine.render("code_review", {
            "language": "javascript",
            "code": "console.log('hello');"
        })
        
        user_content = result["messages"][1]["content"]
        assert "javascript" in user_content
        assert "console.log" in user_content
        assert "Bugs" in user_content or "bugs" in user_content

    def test_render_explain_code_template(self):
        """Test the explain_code template."""
        engine = TemplateEngine()
        
        result = engine.render("explain_code", {
            "language": "rust",
            "code": "fn main() {}"
        })
        
        system_content = result["messages"][0]["content"]
        user_content = result["messages"][1]["content"]
        
        assert "tutor" in system_content.lower()
        assert "rust" in user_content
        assert "fn main()" in user_content

    def test_render_summarize_text_with_default(self):
        """Test summarize_text with default max_sentences."""
        engine = TemplateEngine()
        
        result = engine.render("summarize_text", {
            "text": "A very long article about something interesting..."
        })
        
        content = result["messages"][1]["content"]
        assert "3 sentences" in content  # default value

    def test_render_with_custom_max_sentences(self):
        """Test summarize_text with custom max_sentences."""
        engine = TemplateEngine()
        
        result = engine.render("summarize_text", {
            "text": "Article text...",
            "max_sentences": "5"
        })
        
        content = result["messages"][1]["content"]
        assert "5 sentences" in content

    def test_render_translate_template(self):
        """Test the translate template."""
        engine = TemplateEngine()
        
        result = engine.render("translate", {
            "source_lang": "French",
            "target_lang": "German",
            "text": "Bonjour le monde"
        })
        
        content = result["messages"][1]["content"]
        assert "French" in content
        assert "German" in content
        assert "Bonjour le monde" in content

    def test_render_debug_error_with_defaults(self):
        """Test debug_error template with optional variables."""
        engine = TemplateEngine()
        
        result = engine.render("debug_error", {
            "error": "NullPointerException"
        })
        
        content = result["messages"][1]["content"]
        assert "NullPointerException" in content
        # Should use defaults for optional fields
        assert "Not specified" in content or "Not provided" in content

    def test_render_template_not_found(self):
        """Test that rendering a non-existent template raises an error."""
        engine = TemplateEngine()
        
        with pytest.raises(TemplateNotFoundError):
            engine.render("nonexistent", {})

    def test_list_templates(self):
        """Test listing all templates."""
        engine = TemplateEngine()
        templates = engine.list_templates()
        
        assert isinstance(templates, dict)
        assert "code_review" in templates
        assert "explain_code" in templates
        
        # Check metadata structure
        for name, metadata in templates.items():
            assert "description" in metadata
            assert "variables" in metadata

    def test_get_template(self):
        """Test getting a specific template."""
        engine = TemplateEngine()
        template = engine.get_template("code_review")
        
        assert template is not None
        assert template.name == "code_review"
        assert "language" in template.variables
        assert "code" in template.variables

    def test_get_template_not_found(self):
        """Test getting a non-existent template returns None."""
        engine = TemplateEngine()
        template = engine.get_template("nonexistent")
        assert template is None

    def test_validate_variables_all_provided(self):
        """Test validation when all variables are provided."""
        engine = TemplateEngine()
        missing = engine.validate_variables(
            "code_review",
            {"language": "python", "code": "print('hello')"}
        )
        
        assert missing == []

    def test_validate_variables_missing(self):
        """Test validation when variables are missing."""
        engine = TemplateEngine()
        missing = engine.validate_variables(
            "translate",
            {"source_lang": "en"}  # missing target_lang and text
        )
        
        assert "target_lang" in missing
        assert "text" in missing

    def test_validate_variables_with_defaults(self):
        """Test that variables with defaults are not considered missing."""
        engine = TemplateEngine()
        missing = engine.validate_variables(
            "summarize_text",
            {"text": "Some text"}  # max_sentences has default
        )
        
        assert "max_sentences" not in missing
        assert missing == []

    def test_validate_template_not_found(self):
        """Test validation for non-existent template."""
        engine = TemplateEngine()
        missing = engine.validate_variables("nonexistent", {})
        
        assert missing == []


class TestGlobalTemplateEngine:
    """Tests for the global template engine functions."""

    def test_init_template_engine(self):
        """Test initializing the global template engine."""
        engine = init_template_engine()
        
        assert engine is not None
        assert "code_review" in engine.list_templates()

    def test_get_template_engine_auto_init(self):
        """Test that get_template_engine auto-initializes."""
        # First init with fresh engine
        init_template_engine()
        
        engine = get_template_engine()
        assert engine is not None
        assert "code_review" in engine.list_templates()

    def test_get_template_engine_returns_same_instance(self):
        """Test that get_template_engine returns the same instance."""
        engine1 = get_template_engine()
        engine2 = get_template_engine()
        
        assert engine1 is engine2

    def test_init_with_custom_templates(self):
        """Test init with custom templates."""
        custom = {
            "custom_test": {
                "description": "Test",
                "user_prompt": "Test {{ var }}",
            }
        }
        
        engine = init_template_engine(custom)
        assert "custom_test" in engine.list_templates()


class TestTemplateEdgeCases:
    """Tests for edge cases and error handling."""

    def test_render_with_extra_variables(self):
        """Test rendering with variables not in template."""
        engine = TemplateEngine()
        
        result = engine.render("code_review", {
            "language": "python",
            "code": "print('hello')",
            "extra_var": "ignored"  # Not in template
        })
        
        # Should work fine, just ignore extra
        assert "messages" in result

    def test_render_with_empty_string_variable(self):
        """Test rendering with empty string variables."""
        engine = TemplateEngine()
        
        result = engine.render("code_review", {
            "language": "",
            "code": ""
        })
        
        # Should work with empty strings
        assert "messages" in result

    def test_render_with_special_characters(self):
        """Test rendering with special characters in variables."""
        engine = TemplateEngine()
        
        result = engine.render("code_review", {
            "language": "c++",
            "code": "int main() { return 0; }"
        })
        
        assert "c++" in result["messages"][1]["content"]
        assert "int main()" in result["messages"][1]["content"]

    def test_render_with_unicode(self):
        """Test rendering with unicode characters."""
        engine = TemplateEngine()
        
        result = engine.render("translate", {
            "source_lang": "Japanese",
            "target_lang": "English",
            "text": "こんにちは世界"
        })
        
        assert "こんにちは世界" in result["messages"][1]["content"]

    def test_render_with_numbers(self):
        """Test rendering with numeric variables converted to strings."""
        engine = TemplateEngine()
        
        result = engine.render("summarize_text", {
            "text": "Article",
            "max_sentences": 5  # Integer
        })
        
        assert "5 sentences" in result["messages"][1]["content"]

    def test_variable_extraction_no_duplicates(self):
        """Test that duplicate variables are removed."""
        engine = TemplateEngine()
        template = engine.get_template("refactor")
        # refactor template has 'language' and 'code' variables
        assert "language" in template.variables
        assert "code" in template.variables
        # goals has default, should still be in variables list

    def test_template_without_system_prompt(self):
        """Test rendering a template without system prompt."""
        engine = TemplateEngine()
        # Create a custom template without system_prompt
        custom = {
            "no_system": {
                "description": "No system prompt",
                "user_prompt": "Just {{ text }}",
            }
        }
        engine = TemplateEngine(custom)
        result = engine.render("no_system", {"text": "hello"})
        
        # Should only have user message
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "user"


# API Endpoint Tests
@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from fastapi.testclient import TestClient
    from llmproxy.server import app
    return TestClient(app)


class TestTemplateEndpoints:
    """Tests for the REST API template endpoints."""

    def test_list_templates_endpoint(self, client):
        """Test GET /templates endpoint."""
        response = client.get("/templates")
        assert response.status_code == 200
        
        data = response.json()
        assert "templates" in data
        assert "code_review" in data["templates"]
        assert "explain_code" in data["templates"]

    def test_render_template_endpoint(self, client):
        """Test POST /templates/render endpoint."""
        response = client.post("/templates/render", json={
            "template": "explain_code",
            "variables": {
                "language": "python",
                "code": "def hello(): print('hi')"
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) == 2

    def test_render_template_endpoint_missing_template(self, client):
        """Test render endpoint with missing template field."""
        response = client.post("/templates/render", json={
            "variables": {"language": "python"}
        })
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_render_template_endpoint_invalid_template(self, client):
        """Test render endpoint with non-existent template."""
        response = client.post("/templates/render", json={
            "template": "nonexistent",
            "variables": {}
        })
        
        assert response.status_code == 400
        assert "error" in response.json()

    def test_validate_template_endpoint_valid(self, client):
        """Test POST /templates/validate endpoint with valid variables."""
        response = client.post("/templates/validate", json={
            "template": "code_review",
            "variables": {
                "language": "python",
                "code": "print('hello')"
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["missing_variables"] == []

    def test_validate_template_endpoint_invalid(self, client):
        """Test validate endpoint with missing variables."""
        response = client.post("/templates/validate", json={
            "template": "translate",
            "variables": {
                "source_lang": "en"
                # missing target_lang and text
            }
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "target_lang" in data["missing_variables"]
        assert "text" in data["missing_variables"]

    def test_validate_template_endpoint_missing_template(self, client):
        """Test validate endpoint with missing template field."""
        response = client.post("/templates/validate", json={
            "variables": {"language": "python"}
        })
        
        assert response.status_code == 400
        assert "error" in response.json()
