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

import mock

from rally.benchmark.context.quotas import neutron_quotas as quotas
from tests import test


class NeutronQuotasTestCase(test.TestCase):

    @mock.patch("rally.benchmark.context.quotas.quotas.osclients.Clients")
    def test_update(self, client_mock):
        neutron_quotas = quotas.NeutronQuotas(client_mock)
        tenant_id = mock.MagicMock()
        quotas_values = {
            "network": 20,
            "subnet": 20,
            "port": 100,
            "router": 20,
            "floatingip": 100,
            "security_group": 100,
            "security_group_rule": 100
        }
        neutron_quotas.update(tenant_id, **quotas_values)
        body = {"quota": quotas_values}
        client_mock.neutron().update_quota.assert_called_once_with(tenant_id,
                                                                   body=body)

    @mock.patch("rally.benchmark.context.quotas.quotas.osclients.Clients")
    def test_delete(self, client_mock):
        neutron_quotas = quotas.NeutronQuotas(client_mock)
        tenant_id = mock.MagicMock()
        neutron_quotas.delete(tenant_id)
        client_mock.neutron().delete_quota.assert_called_once_with(tenant_id)
