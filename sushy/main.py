# Copyright 2017 Red Hat, Inc.
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
import collections
import logging

import pkg_resources
import requests

from sushy import auth as sushy_auth
from sushy import connector as sushy_connector
from sushy import exceptions
from sushy.resources import base
from sushy.resources.chassis import chassis
from sushy.resources.compositionservice import compositionservice
from sushy.resources.fabric import fabric
from sushy.resources.manager import manager
from sushy.resources.registry import message_registry
from sushy.resources.registry import message_registry_file
from sushy.resources.sessionservice import session
from sushy.resources.sessionservice import sessionservice
from sushy.resources.system import system
from sushy.resources.updateservice import updateservice
from sushy import utils

LOG = logging.getLogger(__name__)

STANDARD_REGISTRY_PATH = 'standard_registries/'


class ProtocolFeaturesSupportedField(base.CompositeField):

    excerpt_query = base.Field('ExcerptQuery')
    """The excerpt query parameter is supported"""

    expand_query = base.Field('ExpandQuery')
    """The expand query parameter is supported"""

    filter_query = base.Field('FilterQuery')
    """The filter query parameter is supported"""

    only_member_query = base.Field('OnlyMemberQuery')
    """The only query parameter is supported"""

    select_query = base.Field('SelectQuery')
    """The select query parameter is supported"""


class LazyRegistries(collections.abc.MutableMapping):
    """Download registries on demand.

    Redfish message registries can be very large. On top of that,
    they are not used frequently. Thus, let's not pull them off
    the BMC unless the consumer is actually trying to use them.

    :param service_root: Redfish service root object
    :type service_root: sushy.main.Sushy
    """

    def __init__(self, service_root):
        self._service_root = service_root
        self._registries = None

    def __getitem__(self, key):
        registries = self.registries
        return registries[key]

    def __setitem__(self, key, value):
        registries = self.registries
        registries[key] = value

    def __delitem__(self, key):
        registries = self.registries
        del registries[key]

    def __iter__(self):
        registries = self.registries
        return iter(registries or ())

    def __len__(self):
        registries = self.registries
        return len(registries)

    @property
    def registries(self):
        if self._registries is None:
            self._registries = self._service_root.registries

        return self._registries


class Sushy(base.ResourceBase):

    identity = base.Field('Id', required=True)
    """The Redfish root service identity"""

    name = base.Field('Name')
    """The Redfish root service name"""

    uuid = base.Field('UUID')
    """The Redfish root service UUID"""

    product = base.Field('Product')
    """The product associated with this Redfish service"""

    protocol_features_supported = ProtocolFeaturesSupportedField(
        'ProtocolFeaturesSupported')
    """The information about protocol features supported by the service"""

    _composition_service_path = base.Field(
        ['CompositionService', '@odata.id'])
    """CompositionService path"""

    _systems_path = base.Field(['Systems', '@odata.id'])
    """SystemCollection path"""

    _managers_path = base.Field(['Managers', '@odata.id'])
    """ManagerCollection path"""

    _chassis_path = base.Field(['Chassis', '@odata.id'])
    """ChassisCollection path"""

    _fabrics_path = base.Field(['Fabrics', '@odata.id'])
    """FabricCollection path"""

    _session_service_path = base.Field(['SessionService', '@odata.id'])
    """SessionService path"""

    _registries_path = base.Field(['Registries', '@odata.id'])
    """Registries path"""

    _update_service_path = base.Field(['UpdateService', '@odata.id'])
    """UpdateService path"""

    def __init__(self, base_url, username=None, password=None,
                 root_prefix='/redfish/v1/', verify=True,
                 auth=None, connector=None,
                 public_connector=None,
                 language='en'):
        """A class representing a RootService

        :param base_url: The base URL to the Redfish controller. It
            should include scheme and authority portion of the URL. For
            example: https://mgmt.vendor.com
        :param username: User account with admin/server-profile access
            privilege
        :param password: User account password
        :param root_prefix: The default URL prefix. This part includes
            the root service and version. Defaults to /redfish/v1
        :param verify: Either a boolean value, a path to a CA_BUNDLE
            file or directory with certificates of trusted CAs. If set to
            True the driver will verify the host certificates; if False
            the driver will ignore verifying the SSL certificate; if it's
            a path the driver will use the specified certificate or one of
            the certificates in the directory. Defaults to True.
        :param auth: An authentication mechanism to utilize.
        :param connector: A user-defined connector object. Defaults to None.
        :param public_connector: A user-defined connector to use for requests
            on the Internet, e.g., for Message Registries. Defaults to None.
        :param language: RFC 5646 language code for Message Registries.
            Defaults to 'en'.
        """
        self._root_prefix = root_prefix
        if (auth is not None and (password is not None
                                  or username is not None)):
            msg = ('Username or Password were provided to Sushy '
                   'when an authentication mechanism was specified.')
            raise ValueError(msg)
        if auth is None:
            auth = sushy_auth.SessionOrBasicAuth(username=username,
                                                 password=password)
        self._auth = auth

        super(Sushy, self).__init__(
            connector or sushy_connector.Connector(base_url, verify=verify),
            path=self._root_prefix)
        self._public_connector = public_connector or requests
        self._language = language
        self._base_url = base_url
        self._auth.set_context(self, self._conn)
        self._auth.authenticate()

    def __del__(self):
        if self._auth:
            try:
                self._auth.close()

            except Exception as ex:
                LOG.warning('Ignoring error while closing Redfish session '
                            'with %s: %s', self._base_url, ex)
            self._auth = None

    def _parse_attributes(self, json_doc):
        """Parse the attributes of a resource.

        Parsed JSON fields are set to `self` as declared in the class.

        :param json_doc: parsed JSON document in form of Python types
        """
        super(Sushy, self)._parse_attributes(json_doc)
        self.redfish_version = json_doc.get('RedfishVersion')

    def get_system_collection(self):
        """Get the SystemCollection object

        :raises: MissingAttributeError, if the collection attribute is
            not found
        :returns: a SystemCollection object
        """
        if not self._systems_path:
            raise exceptions.MissingAttributeError(
                attribute='Systems/@odata.id', resource=self._path)

        return system.SystemCollection(
            self._conn, self._systems_path,
            redfish_version=self.redfish_version,
            registries=self.lazy_registries)

    def get_system(self, identity=None):
        """Given the identity return a System object

        :param identity: The identity of the System resource. If not given,
            sushy will default to the single available System or fail
            if there appear to be more or less then one System listed.
        :raises: `UnknownDefaultError` if default system can't be determined.
        :returns: The System object
        """
        if identity is None:
            systems_collection = self.get_system_collection()
            listed_systems = systems_collection.get_members()
            if len(listed_systems) != 1:
                raise exceptions.UnknownDefaultError(
                    entity='ComputerSystem',
                    error='System count is not exactly one')

            identity = listed_systems[0].path

        return system.System(self._conn, identity,
                             redfish_version=self.redfish_version,
                             registries=self.lazy_registries)

    def get_chassis_collection(self):
        """Get the ChassisCollection object

        :raises: MissingAttributeError, if the collection attribute is
            not found
        :returns: a ChassisCollection object
        """
        if not self._chassis_path:
            raise exceptions.MissingAttributeError(
                attribute='Chassis/@odata.id', resource=self._path)

        return chassis.ChassisCollection(self._conn, self._chassis_path,
                                         redfish_version=self.redfish_version,
                                         registries=self.lazy_registries)

    def get_chassis(self, identity=None):
        """Given the identity return a Chassis object

        :param identity: The identity of the Chassis resource. If not given,
            sushy will default to the single available chassis or fail
            if there appear to be more or less then one Chassis listed.
        :raises: `UnknownDefaultError` if default system can't be determined.
        :returns: The Chassis object
        """
        if identity is None:
            chassis_collection = self.get_chassis_collection()
            listed_chassis = chassis_collection.get_members()
            if len(listed_chassis) != 1:
                raise exceptions.UnknownDefaultError(
                    entity='Chassis',
                    error='Chassis count is not exactly one')

            identity = listed_chassis[0].path

        return chassis.Chassis(self._conn, identity,
                               redfish_version=self.redfish_version,
                               registries=self.lazy_registries)

    def get_fabric_collection(self):
        """Get the FabricCollection object

        :raises: MissingAttributeError, if the collection attribute is
            not found
        :returns: a FabricCollection object
        """
        if not self._fabrics_path:
            raise exceptions.MissingAttributeError(
                attribute='Fabrics/@odata.id', resource=self._path)

        return fabric.FabricCollection(self._conn, self._fabrics_path,
                                       redfish_version=self.redfish_version,
                                       registries=self.lazy_registries)

    def get_fabric(self, identity):
        """Given the identity return a Fabric object

        :param identity: The identity of the Fabric resource
        :returns: The Fabric object
        """
        return fabric.Fabric(self._conn, identity,
                             redfish_version=self.redfish_version,
                             registries=self.lazy_registries)

    def get_manager_collection(self):
        """Get the ManagerCollection object

        :raises: MissingAttributeError, if the collection attribute is
            not found
        :returns: a ManagerCollection object
        """
        if not self._managers_path:
            raise exceptions.MissingAttributeError(
                attribute='Managers/@odata.id', resource=self._path)

        return manager.ManagerCollection(self._conn, self._managers_path,
                                         redfish_version=self.redfish_version,
                                         registries=self.lazy_registries)

    def get_manager(self, identity=None):
        """Given the identity return a Manager object

        :param identity: The identity of the Manager resource. If not given,
            sushy will default to the single available Manager or fail
            if there appear to be more or less then one Manager listed.
        :returns: The Manager object
        """
        if identity is None:
            managers_collection = self.get_manager_collection()
            listed_managers = managers_collection.get_members()
            if len(listed_managers) != 1:
                raise exceptions.UnknownDefaultError(
                    entity='Manager',
                    error='Manager count is not exactly one')

            identity = listed_managers[0].path

        return manager.Manager(self._conn, identity,
                               redfish_version=self.redfish_version,
                               registries=self.lazy_registries)

    def get_session_service(self):
        """Get the SessionService object

        :raises: MissingAttributeError, if the collection attribute is
            not found
        :returns: as SessionCollection object
        """
        if not self._session_service_path:
            raise exceptions.MissingAttributeError(
                attribute='SessionService/@odata.id', resource=self._path)

        return sessionservice.SessionService(
            self._conn, self._session_service_path,
            redfish_version=self.redfish_version)

    def get_sessions_path(self):
        """Returns the Sessions url"""

        try:
            links_url = self.json.get('Links')
            return links_url['Sessions']['@odata.id']
        except (TypeError, KeyError):
            raise exceptions.MissingAttributeError(
                attribute='Links/Sessions/@data.id', resource=self.path)

    def get_session(self, identity):
        """Given the identity return a Session object

        :param identity: The identity of the session resource
        :returns: The Session object
        """
        return session.Session(
            self._conn, identity,
            redfish_version=self.redfish_version,
            registries=self.lazy_registries)

    def get_update_service(self):
        """Get the UpdateService object

        :returns: The UpdateService object
        """
        if not self._update_service_path:
            raise exceptions.MissingAttributeError(
                attribute='UpdateService/@odata.id', resource=self._path)

        return updateservice.UpdateService(
            self._conn, self._update_service_path,
            redfish_version=self.redfish_version,
            registries=self.lazy_registries)

    def _get_registry_collection(self):
        """Get MessageRegistryFileCollection object

        This resource is optional and can be empty.

        :returns: MessageRegistryFileCollection object
            or None if Registries not provided
        """

        if self._registries_path:
            return message_registry_file.MessageRegistryFileCollection(
                self._conn,
                self._registries_path,
                redfish_version=self.redfish_version)

    def get_composition_service(self):
        """Get the CompositionService object

        :raises: MissingAttributeError, if the composition service
            attribute is not found
        :returns: The CompositionService object
        """
        if not self._composition_service_path:
            raise exceptions.MissingAttributeError(
                attribute='CompositionService/@odata.id',
                resource=self._path)

        return compositionservice.CompositionService(
            self._conn, self._composition_service_path,
            redfish_version=self.redfish_version,
            registries=self.lazy_registries)

    def _get_standard_message_registry_collection(self):
        """Load packaged standard message registries

        :returns: list of MessageRegistry
        """

        message_registries = []
        resource_package_name = __name__
        for json_file in pkg_resources.resource_listdir(
                resource_package_name, STANDARD_REGISTRY_PATH):
            # Not using path.join according to pkg_resources docs
            mes_reg = message_registry.MessageRegistry(
                None, STANDARD_REGISTRY_PATH + json_file,
                reader=base.JsonPackagedFileReader(
                    resource_package_name))
            message_registries.append(mes_reg)

        return message_registries

    @property
    @utils.cache_it
    def registries(self):
        """Gets and combines all message registries together

        Fetches all registries if any provided by Redfish service
        and combines together with packaged standard registries.

        :returns: dict of combined message registries keyed by both the
            registry name (Registry_name.Major_version.Minor_version) and the
            message registry file identity, with the value being the actual
            registry itself.
        """
        standard = self._get_standard_message_registry_collection()

        registries = {r.registry_prefix + '.'
                      + r.registry_version.rsplit('.', 1)[0]: r
                      for r in standard if r.language == self._language}

        registry_col = self._get_registry_collection()

        if registry_col:
            provided = registry_col.get_members()
            for r in provided:
                message_registry = r.get_message_registry(
                    self._language,
                    self._public_connector)
                registries[r.registry] = message_registry
                if r.identity not in registries:
                    registries[r.identity] = message_registry

        return registries

    @property
    def lazy_registries(self):
        """Gets and combines all message registries together

        Fetches all registries if any provided by Redfish service
        and combines together with packaged standard registries.

        :returns: dict of combined message registries where key is
            Registry_name.Major_version.Minor_version and value is registry
            itself.
        """
        return LazyRegistries(self)
