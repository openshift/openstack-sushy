# Sushy Development Guide for Claude

## Project Overview

Sushy is a Python library for communicating with Redfish-based BMC (Baseboard Management Controller) systems. It is part of the OpenStack ecosystem, specifically supporting the Ironic bare metal provisioning project.

**Key Design Principles:**
- Extremely simple and small
- Minimal dependencies
- Conservative with BMC requests (BMCs are flaky)
- Scope limited to OpenStack Ironic requirements

**Redfish**: An industry-standard RESTful API specification by DMTF for managing servers, storage, and networking equipment. Schemas are available at https://redfish.dmtf.org/schemas/

## Project Structure

```
sushy/
├── __init__.py              # Exports all public constants and Sushy class
├── main.py                  # Main Sushy entry point class
├── auth.py                  # Authentication handling
├── connector.py             # HTTP connection management
├── exceptions.py            # Custom exceptions
├── utils.py                 # Utility functions
├── taskmonitor.py           # Task monitoring for async operations
├── resources/               # Redfish resource implementations
│   ├── base.py              # Base classes: Field, ResourceBase, etc.
│   ├── common.py            # Common field types (StatusField, ActionField)
│   ├── constants.py         # Shared enums (Health, State, ResetType, etc.)
│   ├── system/              # ComputerSystem resources
│   ├── manager/             # Manager resources
│   ├── chassis/             # Chassis resources
│   ├── storage/             # Storage resources (if separate)
│   └── ...                  # Other resource categories
├── oem/                     # OEM-specific extensions
│   └── dell/                # Dell iDRAC extensions
├── standard_registries/     # Bundled Redfish message registries
└── tests/
    └── unit/
        ├── base.py          # Test base class (extends oslotest)
        ├── json_samples/    # Sample JSON responses for testing
        └── resources/       # Unit tests mirroring resources/ structure
```

## Coding Conventions

### Style
- **Line length**: 79 characters (PEP 8)
- **Linting**: ruff + flake8 with OpenStack hacking rules
- **Python version**: 3.7+ (see pyproject.toml)
- Run linting: `tox -e pep8`
- Run tests: `tox -e py3` or `stestr run`

### License Header
All Python files must include the Apache 2.0 license header:
```python
# Copyright <YEAR> <AUTHOR>
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
```

### Imports
Follow OpenStack import ordering (pep8 style):
1. Standard library
2. Third-party libraries
3. Local imports (sushy.*)

## Resource Implementation Patterns

### 1. Field Types (from `sushy/resources/base.py`)

| Field Type | Use Case | Example |
|------------|----------|---------|
| `Field(path)` | Simple JSON property | `name = Field('Name')` |
| `Field(path, adapter=func)` | With transformation | `size = Field('Size', adapter=int)` |
| `Field(path, required=True)` | Required field | `identity = Field('Id', required=True)` |
| `MappedField(path, enum)` | Enum mapping | `state = MappedField('State', Health)` |
| `MappedListField(path, enum)` | List of enums | `types = MappedListField('Types', MyEnum)` |
| `CompositeField(path)` | Nested object | See StatusField example |
| `ListField(path)` | List of objects | See MessageListField example |
| `DictionaryField(path)` | Dict of objects | For key-value structures |

### 2. Simple Resource Example

```python
from sushy.resources import base
from sushy.resources import common
from sushy.resources import constants as res_cons
from sushy.resources.myresource import constants as my_cons

class MyResource(base.ResourceBase):
    """A class representing MyResource."""

    identity = base.Field('Id', required=True)
    """The resource identity string"""

    name = base.Field('Name')
    """The resource name"""

    description = base.Field('Description')
    """The resource description"""

    status = common.StatusField('Status')
    """The resource status"""

    my_enum_field = base.MappedField('MyEnumField', my_cons.MyEnum)
    """Field mapped to an enumeration"""

    def __init__(self, connector, path, redfish_version=None,
                 registries=None, root=None):
        super().__init__(connector, path, redfish_version=redfish_version,
                         registries=registries, root=root)
```

### 3. Composite Field Example

```python
class BootField(base.CompositeField):
    """Boot configuration field."""

    enabled = base.MappedField('BootSourceOverrideEnabled',
                               sys_cons.BootSourceOverrideEnabled)
    target = base.MappedField('BootSourceOverrideTarget',
                              sys_cons.BootSource)
    mode = base.MappedField('BootSourceOverrideMode',
                            sys_cons.BootSourceOverrideMode)
    allowed_values = base.Field(
        'BootSourceOverrideTarget@Redfish.AllowableValues',
        adapter=list)
```

### 4. Action Field Example

```python
class ActionsField(base.CompositeField):
    reset = common.ResetActionField('#ComputerSystem.Reset')

# In ResetActionField (common.py):
class ResetActionField(ActionField):
    allowed_values = base.Field('ResetType@Redfish.AllowableValues',
                                adapter=list)
```

### 5. Sub-Resource Properties (Lazy Loading)

```python
@property
@utils.cache_it
def processors(self):
    """Property to reference ProcessorCollection instance."""
    return processor.ProcessorCollection(
        self._conn,
        utils.get_sub_resource_path_by(self, 'Processors'),
        redfish_version=self.redfish_version,
        registries=self.registries,
        root=self.root)
```

### 6. Resource Collection Example

```python
class MyResourceCollection(base.ResourceCollectionBase):

    @property
    def _resource_type(self):
        return MyResource

    def __init__(self, connector, path, redfish_version=None,
                 registries=None, root=None):
        super().__init__(connector, path, redfish_version=redfish_version,
                         registries=registries, root=root)
```

### 7. Constants/Enums Pattern

```python
import enum

class MyEnum(enum.Enum):
    """Description of what this enum represents."""

    VALUE_ONE = 'ValueOne'
    """Description of ValueOne."""

    VALUE_TWO = 'ValueTwo'
    """Description of ValueTwo."""

# Backward compatibility (optional, for existing enums)
MY_ENUM_VALUE_ONE = MyEnum.VALUE_ONE
MY_ENUM_VALUE_TWO = MyEnum.VALUE_TWO
```

**Naming Convention for Enum Members:**
- Convert CamelCase to UPPER_SNAKE_CASE
- Example: `GracefulShutdown` → `GRACEFUL_SHUTDOWN`

## Testing Patterns

### Test File Structure

```python
import json
from unittest import mock

from sushy.resources.myresource import myresource
from sushy.tests.unit import base


class MyResourceTestCase(base.TestCase):

    def setUp(self):
        super().setUp()
        self.conn = mock.Mock()
        with open('sushy/tests/unit/json_samples/myresource.json') as f:
            self.json_doc = json.load(f)
        self.conn.get.return_value.json.return_value = self.json_doc

        self.resource = myresource.MyResource(
            self.conn, '/redfish/v1/MyResource/1',
            redfish_version='1.0.2')

    def test__parse_attributes(self):
        self.resource._parse_attributes(self.json_doc)
        self.assertEqual('1', self.resource.identity)
        self.assertEqual('My Resource Name', self.resource.name)
```

### JSON Sample Files

Place in `sushy/tests/unit/json_samples/<resource>.json`:
```json
{
    "@odata.type": "#MyResource.v1_0_0.MyResource",
    "@odata.id": "/redfish/v1/MyResource/1",
    "Id": "1",
    "Name": "My Resource Name",
    "Status": {
        "State": "Enabled",
        "Health": "OK"
    }
}
```

## Existing Tools

### `tools/generate-enum.py`

Generates Python enum classes from Redfish JSON schemas:

```bash
# From URL
python tools/generate-enum.py \
    https://redfish.dmtf.org/schemas/v1/ComputerSystem.v1_10_0.json \
    SystemType

# From local file
python tools/generate-enum.py ./schema.json MyEnumName

# With backward compatibility constants
python tools/generate-enum.py <url> <name> --compat
```

## Common Adapters

Used in `Field(path, adapter=...)`:

| Adapter | Purpose |
|---------|---------|
| `int` | Convert to integer |
| `list` | Ensure list type |
| `utils.int_or_none` | Integer or None |
| `parser.parse` | Parse ISO datetime (from dateutil) |
| `utils.get_members_identities` | Extract @odata.id from Members array |

## Key Files Reference

| File | Purpose |
|------|---------|
| `sushy/resources/base.py` | Field classes, ResourceBase, ResourceCollectionBase |
| `sushy/resources/common.py` | StatusField, ActionField, ResetActionField |
| `sushy/resources/constants.py` | Shared enums (Health, State, ResetType, etc.) |
| `sushy/utils.py` | Helpers: cache_it, get_sub_resource_path_by, etc. |
| `sushy/__init__.py` | Public exports (add new constants imports here) |

## Adding a New Resource

1. **Create constants file** (if enums needed): `sushy/resources/<category>/constants.py`
2. **Create resource file**: `sushy/resources/<category>/<resource>.py`
3. **Update `__init__.py`** files for exports
4. **Add to `sushy/__init__.py`** if constants should be public
5. **Create JSON sample**: `sushy/tests/unit/json_samples/<resource>.json`
6. **Create unit tests**: `sushy/tests/unit/resources/<category>/test_<resource>.py`

## Redfish Schema to Sushy Mapping

| Schema Element | Sushy Implementation |
|----------------|---------------------|
| Simple property (string, integer, boolean) | `base.Field('PropertyName')` |
| Enum property | `base.MappedField('PropertyName', EnumClass)` |
| Nested object | Custom `CompositeField` subclass |
| Array of objects | Custom `ListField` subclass |
| `@odata.id` reference | Property with `utils.get_sub_resource_path_by()` |
| Action with AllowableValues | `ActionField` subclass with `allowed_values` |
| Collection (`Members` array) | `ResourceCollectionBase` subclass |

## OpenStack Conventions

- Use `LOG = logging.getLogger(__name__)` for logging
- Tests extend `sushy.tests.unit.base.TestCase` (wraps oslotest)
- Mock HTTP connector in tests, don't make real requests
- Use `mock.patch.object()` with `autospec=True` when possible


