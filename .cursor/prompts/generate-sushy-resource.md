# Generate Sushy Resource

Generate or update Sushy Python resource files from a DMTF Redfish JSON schema.

## Input

Provide the schema as one of:
- **URL**: A Redfish schema URL (e.g., `https://redfish.dmtf.org/schemas/v1/Storage.v1_15_0.json`)
- **File path**: Local path to a schema JSON file
- **Pasted content**: The schema JSON directly in the conversation

## What to Generate

Specify what you need (default: all):
- `constants` - Enum constants only
- `resource` - Resource class only
- `tests` - Test file and JSON sample only
- `all` - Everything

## Instructions

Follow these steps using the patterns documented in `CLAUDE.md`:

### 1. Fetch and Parse Schema

- If URL provided, fetch the schema JSON
- Extract resource name from `definitions` or `@odata.type`
- Identify version from filename or schema

### 2. Identify Target Directory

Map resource to existing Sushy structure:
- ComputerSystem → `resources/system/`
- Storage, Drive, Volume → `resources/system/storage/`
- Manager → `resources/manager/`
- Chassis → `resources/chassis/`
- Processor → `resources/system/`
- Fabric, Endpoint → `resources/fabric/`
- Certificate → `resources/certificateservice/`
- Task → `resources/taskservice/`
- Event → `resources/eventservice/`
- Update → `resources/updateservice/`

### 3. Generate Constants (if enums exist)

For each `enum` in schema definitions:

```python
class EnumName(enum.Enum):
    """Description from schema."""

    UPPER_SNAKE_VALUE = 'OriginalValue'
    """Description from enumDescriptions."""
```

### 4. Generate Resource Class

Create resource extending `base.ResourceBase`:

```python
class ResourceName(base.ResourceBase):
    identity = base.Field('Id', required=True)
    name = base.Field('Name')
    # Map all properties from schema
```

Field type mapping:
| Schema | Sushy |
|--------|-------|
| `string` | `base.Field('Name')` |
| `integer` | `base.Field('Name', adapter=int)` |
| `enum $ref` | `base.MappedField('Name', EnumClass)` |
| `object $ref` | Custom `CompositeField` |
| `array of objects` | Custom `ListField` |
| `date-time` | `base.Field('Name', adapter=parser.parse)` |

### 5. Generate Actions (if present)

For `Actions` in schema, create action methods.

### 6. Generate Collection (if applicable)

If schema defines a collection, create `ResourceCollectionBase` subclass.

### 7. Generate Tests

Create:
- `sushy/tests/unit/json_samples/<resource>.json`
- `sushy/tests/unit/resources/<category>/test_<resource>.py`

### 8. Update Exports

Update `__init__.py` files as needed.

## Output

Provide the generated code in clearly labeled sections. Ask for confirmation before creating/modifying files.

## Reference

See `CLAUDE.md` for complete Sushy patterns and conventions.

