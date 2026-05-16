#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.network_stack import NetworkStack
from stacks.data_lake_stack import DataLakeStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "eu-central-1",
)

network = NetworkStack(app, "NetworkStack", env=env)
DataLakeStack(app, "DataLakeStack", env=env)

app.synth()
