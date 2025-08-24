"""
Tests for core validation system
"""
import pytest
from datetime import date, timedelta
from core.validators import (
    StringValidator, PhoneValidator, EmailValidator, 
    NumberValidator, DateValidator, ChoiceValidator,
    ValidationSchema, CLIENT_SCHEMA, ValidationError
)

class TestStringValidator:
    """Test string validation"""
    
    def test_valid_string(self):
        validator = StringValidator(min_length=2, max_length=10)
        result = validator.validate("test", "field")
        assert result == "test"
    
    def test_string_too_short(self):
        validator = StringValidator(min_length=5)
        with pytest.raises(ValidationError) as exc:
            validator.validate("abc", "field")
        assert "at least 5 characters" in str(exc.value)
    
    def test_string_too_long(self):
        validator = StringValidator(max_length=5)
        with pytest.raises(ValidationError) as exc:
            validator.validate("abcdefgh", "field")
        assert "at most 5 characters" in str(exc.value)
    
    def test_strip_whitespace(self):
        validator = StringValidator(strip_whitespace=True)
        result = validator.validate("  test  ", "field")
        assert result == "test"
    
    def test_html_sanitization(self):
        validator = StringValidator(sanitize_html=True)
        result = validator.validate("<script>alert('xss')</script>", "field")
        assert "&lt;script&gt;" in result

class TestPhoneValidator:
    """Test phone number validation"""
    
    def test_valid_brazilian_phone(self):
        validator = PhoneValidator()
        result = validator.validate("11999999999", "phone")
        assert result == "5511999999999"
    
    def test_phone_with_country_code(self):
        validator = PhoneValidator()
        result = validator.validate("5511999999999", "phone")
        assert result == "5511999999999"
    
    def test_phone_with_formatting(self):
        validator = PhoneValidator()
        result = validator.validate("(11) 99999-9999", "phone")
        assert result == "5511999999999"
    
    def test_invalid_phone_length(self):
        validator = PhoneValidator()
        with pytest.raises(ValidationError) as exc:
            validator.validate("123", "phone")
        assert "valid Brazilian phone" in str(exc.value)

class TestEmailValidator:
    """Test email validation"""
    
    def test_valid_email(self):
        validator = EmailValidator()
        result = validator.validate("test@example.com", "email")
        assert result == "test@example.com"
    
    def test_email_normalization(self):
        validator = EmailValidator()
        result = validator.validate("  TEST@EXAMPLE.COM  ", "email")
        assert result == "test@example.com"
    
    def test_invalid_email(self):
        validator = EmailValidator()
        with pytest.raises(ValidationError) as exc:
            validator.validate("invalid-email", "email")
        assert "valid email address" in str(exc.value)

class TestNumberValidator:
    """Test number validation"""
    
    def test_valid_number(self):
        validator = NumberValidator(min_value=0, max_value=100)
        result = validator.validate(50, "number")
        assert result == 50.0
    
    def test_string_number(self):
        validator = NumberValidator()
        result = validator.validate("42.5", "number")
        assert result == 42.5
    
    def test_brazilian_decimal_format(self):
        validator = NumberValidator()
        result = validator.validate("42,5", "number")
        assert result == 42.5
    
    def test_number_too_small(self):
        validator = NumberValidator(min_value=10)
        with pytest.raises(ValidationError) as exc:
            validator.validate(5, "number")
        assert "at least 10" in str(exc.value)
    
    def test_number_too_large(self):
        validator = NumberValidator(max_value=100)
        with pytest.raises(ValidationError) as exc:
            validator.validate(150, "number")
        assert "at most 100" in str(exc.value)
    
    def test_invalid_number(self):
        validator = NumberValidator()
        with pytest.raises(ValidationError) as exc:
            validator.validate("not-a-number", "number")
        assert "valid number" in str(exc.value)

class TestDateValidator:
    """Test date validation"""
    
    def test_valid_date(self):
        validator = DateValidator()
        result = validator.validate("2025-01-01", "date")
        assert result == date(2025, 1, 1)
    
    def test_brazilian_date_format(self):
        validator = DateValidator()
        result = validator.validate("01/01/2025", "date")
        assert result == date(2025, 1, 1)
    
    def test_date_object(self):
        validator = DateValidator()
        test_date = date(2025, 1, 1)
        result = validator.validate(test_date, "date")
        assert result == test_date
    
    def test_date_too_early(self):
        tomorrow = date.today() + timedelta(days=1)
        validator = DateValidator(min_date=tomorrow)
        with pytest.raises(ValidationError) as exc:
            validator.validate(date.today(), "date")
        assert "cannot be before" in str(exc.value)
    
    def test_invalid_date_format(self):
        validator = DateValidator()
        with pytest.raises(ValidationError) as exc:
            validator.validate("invalid-date", "date")
        assert "valid date" in str(exc.value)

class TestChoiceValidator:
    """Test choice validation"""
    
    def test_valid_choice(self):
        validator = ChoiceValidator(['option1', 'option2', 'option3'])
        result = validator.validate('option2', 'choice')
        assert result == 'option2'
    
    def test_case_insensitive(self):
        validator = ChoiceValidator(['Option1', 'Option2'], case_sensitive=False)
        result = validator.validate('option1', 'choice')
        assert result == 'Option1'  # Returns original case
    
    def test_invalid_choice(self):
        validator = ChoiceValidator(['option1', 'option2'])
        with pytest.raises(ValidationError) as exc:
            validator.validate('option3', 'choice')
        assert "must be one of" in str(exc.value)

class TestValidationSchema:
    """Test validation schema"""
    
    def test_valid_data(self):
        schema = ValidationSchema({
            'name': StringValidator(min_length=2),
            'age': NumberValidator(min_value=0, max_value=150)
        })
        
        data = {'name': 'John', 'age': 30}
        result = schema.validate(data)
        
        assert result['name'] == 'John'
        assert result['age'] == 30.0
    
    def test_missing_required_field(self):
        schema = ValidationSchema({
            'name': StringValidator(required=True)
        })
        
        with pytest.raises(ValidationError) as exc:
            schema.validate({})
        assert "name is required" in str(exc.value)
    
    def test_unexpected_field(self):
        schema = ValidationSchema({
            'name': StringValidator()
        })
        
        with pytest.raises(ValidationError) as exc:
            schema.validate({'name': 'John', 'unexpected': 'value'})
        assert "Unexpected field" in str(exc.value)

class TestClientSchema:
    """Test the predefined CLIENT_SCHEMA"""
    
    def test_valid_client_data(self):
        data = {
            'name': 'João Silva',
            'phone_number': '11999999999',
            'plan_name': 'Premium',
            'plan_price': 50.0,
            'server_info': 'Server A',
            'due_date': date.today() + timedelta(days=30),
            'other_info': 'Additional info'
        }
        
        result = CLIENT_SCHEMA.validate(data)
        
        assert result['name'] == 'João Silva'
        assert result['phone_number'] == '5511999999999'
        assert result['plan_price'] == 50.0
    
    def test_client_data_validation_errors(self):
        data = {
            'name': 'A',  # Too short
            'phone_number': '123',  # Invalid phone
            'plan_name': '',  # Empty
            'plan_price': -10,  # Negative price
            'due_date': date.today() - timedelta(days=1)  # Past date
        }
        
        with pytest.raises(ValidationError):
            CLIENT_SCHEMA.validate(data)