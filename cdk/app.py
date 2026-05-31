#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.network_stack import NetworkStack
from stacks.data_lake_stack import DataLakeStack
from stacks.bronze_stack import BronzeStack
from stacks.silver_stack import SilverStack
from stacks.gold_stack import GoldStack
from stacks.viz_stack import VizStack
from stacks.notif_stack import NotifStack

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

silver = SilverStack(
    app,
    "SilverStack",
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    bucket=data_lake.bucket,
    env=env,
)

viz = VizStack(
    app,
    "VizStack",
    vpc=network.vpc,
    ec2_sg=network.ec2_sg,
    bucket=data_lake.bucket,
    env=env,
)

gold = GoldStack(
    app,
    "GoldStack",
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    bucket=data_lake.bucket,
    ec2_private_ip=viz.ec2_private_ip,
    env=env,
)

NotifStack(
    app,
    "NotifStack",
    silver_state_machine=silver.state_machine,
    gold_state_machine=gold.state_machine,
    discord_webhook_url=app.node.try_get_context("discord_webhook_url") or "",
    env=env,
)

app.synth()
