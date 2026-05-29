#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.network_stack import NetworkStack
from stacks.data_lake_stack import DataLakeStack
from stacks.bronze_stack import BronzeStack
from stacks.silver_stack import SilverStack
from stacks.gold_stack import GoldStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "eu-central-1",
)

network = NetworkStack(app, "NetworkStack", env=env)
data_lake = DataLakeStack(app, "DataLakeStack", env=env)
BronzeStack(
    app,
    "BronzeStack",
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    bucket=data_lake.bucket,
    env=env,
)

SilverStack(
    app,
    "SilverStack",
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    bucket=data_lake.bucket,
    env=env,
)

GoldStack(
    app,
    "GoldStack",
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    bucket=data_lake.bucket,
    env=env,
)

app.synth()
