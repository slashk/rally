# Copyright 2014: Mirantis Inc.
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

from oslo.config import cfg

from rally.benchmark.context import base
from rally.benchmark import utils
from rally.benchmark.wrappers import keystone
from rally import consts
from rally.objects import endpoint
from rally.openstack.common.gettextutils import _
from rally.openstack.common import log as logging
from rally import osclients
from rally import utils as rutils


LOG = logging.getLogger(__name__)

context_opts = [
    cfg.IntOpt("concurrent",
               default=30,
               help="How many concurrent threads use for serving users "
                    "context"),
    cfg.StrOpt("project_domain",
               default="default",
               help="ID of domain in which projects will be created."),
    cfg.StrOpt("user_domain",
               default="default",
               help="ID of domain in which users will be created."),
    cfg.BoolOpt('static_users', default=False, help='use static users'),
]

CONF = cfg.CONF
CONF.register_opts(context_opts,
                   group=cfg.OptGroup(name='users_context',
                                      title='benchmark context options'))


class UserGenerator(base.Context):
    """Context class for generating temporary users/tenants for benchmarks."""

    __ctx_name__ = "users"
    __ctx_order__ = 100
    __ctx_hidden__ = False

    CONFIG_SCHEMA = {
        "type": "object",
        "$schema": rutils.JSON_SCHEMA,
        "properties": {
            "tenants": {
                "type": "integer",
                "minimum": 1
            },
            "users_per_tenant": {
                "type": "integer",
                "minimum": 1
            },
            "concurrent": {
                "type": "integer",
                "minimum": 1
            },
            "project_domain": {
                "type": "string",
            },
            "user_domain": {
                "type": "string",
            },
        },
        "additionalProperties": False
    }
    PATTERN_TENANT = "ctx_rally_%(task_id)s_tenant_%(iter)i"
    PATTERN_USER = "ctx_rally_%(tenant_id)s_user_%(uid)d"

    def __init__(self, context):
        super(UserGenerator, self).__init__(context)
        self.config.setdefault("tenants", 1)
        self.config.setdefault("users_per_tenant", 1)
        self.config.setdefault("concurrent",
                               cfg.CONF.users_context.concurrent)
        self.config.setdefault("project_domain",
                               cfg.CONF.users_context.project_domain)
        self.config.setdefault("user_domain",
                               cfg.CONF.users_context.user_domain)
        self.endpoint = self.context["admin"]["endpoint"]
        self.config.setdefault("static_users",
                               cfg.CONF.users_context.static_users)
        # self.config.setdefault("static_user_names",
        #                        cfg.CONF.users_context.static_user_names)
        # self.config.setdefault("static_tenant_names",
        #                        cfg.CONF.users_context.static_tenant_names)
        # NOTE(boris-42): I think this is the best place for adding logic when
        #                 we are using pre created users or temporary. So we
        #                 should rename this class s/UserGenerator/UserContext/
        #                 and change a bit logic of populating lists of users
        #                 and tenants

    @classmethod
    def _static_user_list(cls, test_user_names, password, admin_endpoint,
                          tenant, project_dom, user_dom):
        """Return static users instead of making temporary users and tenants.

        :returns: list (dict users)
        """

        users = []
        for user_name in test_user_names:
            u = client.users.get_user(user_name)
            user_endpoint = endpoint.Endpoint(client.auth_url, user_name,
                                              password, tenant.name,
                                              consts.EndpointPermission.USER,
                                              client.region_name,
                                              project_domain_name=project_dom,
                                              user_domain_name=user_dom)
            users.append({"id": u.id,
                          "endpoint": user_endpoint,
                          "tenant_id": u.tenantId})
	    LOG.debug("substituting static user: %s, %s" % (u.id, user_endpoint))
        return users

    @classmethod
    def _static_tenant_list(kclient, test_tenant):
        """Return static tenant instead of making temporary users and tenants.

        :param args: keystone client object
        :param args: test_tenant tenant name for test users
        :returns: tenant object
        """

        LOG.debug("substituting static project: %s" % (test_tenant))
        return kclient.tenants.get_project(test_tenant)

    @classmethod
    def _create_tenant_users(cls, args):
        """Create tenant with users and their endpoints.

        This is suitable for using with pool of threads.
        :param args: tuple arguments, for Pool.imap()
        :returns: tuple (dict tenant, list users)
        """

        static_users, admin_endpoint, users_num, project_dom, user_dom, task_id, i = args
        users = []

        client = keystone.wrap(osclients.Clients(admin_endpoint).keystone())
        LOG.debug("Static user model is %s" % static_users)
        if static_users:
            tenant = _static_tenant_list(client, "demo")
        else:
            tenant = client.create_project(
                cls.PATTERN_TENANT % {"task_id": task_id, "iter": i},
                                      project_dom)
        LOG.debug("Creating %d users for tenant %s" % (users_num, tenant.id))
        LOG.debug("Admin endpoint is " % admin_endpoint)

        if static_users:
            # TODO: refactor this ugliness out
            test_user_names = ["test01", "test02", "test03"]
            password = "s3kr1t"
            users = _static_user_list(client, test_user_names, password,
                                      admin_endpoint, tenant, project_dom,
                                      user_dom)
        else:
            for user_id in range(users_num):
		    username = cls.PATTERN_USER % {"tenant_id": tenant.id,
						   "uid": user_id}
		    user = client.create_user(username, "password",
					      "%s@email.me" % username, tenant.id,
					      user_dom)
		    user_endpoint = endpoint.Endpoint(client.auth_url, user.name,
						      "password", tenant.name,
						      consts.EndpointPermission.USER,
						      client.region_name,
						      project_domain_name=project_dom,
						      user_domain_name=user_dom)
		    users.append({"id": user.id,
				  "endpoint": user_endpoint,
				  "tenant_id": tenant.id})

        LOG.debug("tenant: %s, users %s" % (tenant.id, users))

        return ({"id": tenant.id, "name": tenant.name}, users)

    @classmethod
    def _delete_tenants(cls, args):
        """Delete given tenants.

        :param args: tuple arguments, for Pool.imap()
        """
        admin_endpoint, tenants = args
        client = keystone.wrap(osclients.Clients(admin_endpoint).keystone())

        for tenant in tenants:
            try:
                client.delete_project(tenant["id"])
            except Exception as ex:
                LOG.warning("Failed to delete tenant: %(tenant_id)s. "
                            "Exception: %(ex)s" %
                            {"tenant_id": tenant["id"], "ex": ex})

    @classmethod
    def _delete_users(cls, args):
        """Delete given users.

        :param args: tuple arguments, for Pool.imap()
        """
        admin_endpoint, users = args
        client = keystone.wrap(osclients.Clients(admin_endpoint).keystone())

        for user in users:
            try:
                client.delete_user(user["id"])
            except Exception as ex:
                LOG.warning("Failed to delete user: %(user_id)s. "
                            "Exception: %(ex)s" %
                            {"user_id": user["id"], "ex": ex})

    @rutils.log_task_wrapper(LOG.info, _("Enter context: `users`"))
    def setup(self):
        """Create tenants and users, using pool of threads."""

        if not self.config["static_users"]:
		users_num = self.config["users_per_tenant"]
	else:
		# TODO: this should count supplied users
		users_num = 3

        args = [(self.config["static_users"], self.endpoint, users_num, self.config["project_domain"],
                 self.config["user_domain"], self.task["uuid"], i)
                for i in range(self.config["tenants"])]

        LOG.debug("Creating %d users using %s threads" % (
            users_num * self.config["tenants"], self.config["concurrent"]))

        for tenant, users in utils.run_concurrent(
                self.config["concurrent"],
                UserGenerator,
                "_create_tenant_users",
                args):
            self.context["tenants"].append(tenant)
            self.context["users"] += users

    @rutils.log_task_wrapper(LOG.info, _("Exit context: `users`"))
    def cleanup(self):
        """Delete tenants and users, using pool of threads."""

        concurrent = self.config["concurrent"]

	if not self.config["static_users"]:
		# Delete users
		users_chunks = utils.chunks(self.context["users"], concurrent)
		utils.run_concurrent(
		    concurrent,
		    UserGenerator,
		    "_delete_users",
		    [(self.endpoint, users) for users in users_chunks])

		# Delete tenants
		tenants_chunks = utils.chunks(self.context["tenants"], concurrent)
		utils.run_concurrent(
		    concurrent,
		    UserGenerator,
		    "_delete_tenants",
		    [(self.endpoint, tenants) for tenants in tenants_chunks])
