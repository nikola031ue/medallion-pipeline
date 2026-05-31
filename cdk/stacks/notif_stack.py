import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct


class NotifStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        silver_state_machine: sfn.StateMachine,
        gold_state_machine: sfn.StateMachine,
        discord_webhook_url: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        topic = sns.Topic(
            self,
            "PipelineFailureTopic",
            display_name="Medallion Pipeline Failures",
        )

        discord_notifier = lambda_.DockerImageFunction(
            self,
            "DiscordNotifier",
            code=lambda_.DockerImageCode.from_image_asset(
                "../lambdas/notif/discord_notifier"
            ),
            timeout=cdk.Duration.seconds(30),
            memory_size=128,
            environment={
                "DISCORD_WEBHOOK_URL": discord_webhook_url,
            },
        )

        topic.add_subscription(subs.LambdaSubscription(discord_notifier))

        for sm, name in [
            (silver_state_machine, "silver-normalization"),
            (gold_state_machine, "gold-pipeline"),
        ]:
            alarm = cloudwatch.Alarm(
                self,
                f"{name}-failure-alarm",
                metric=cloudwatch.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionsFailed",
                    dimensions_map={"StateMachineArn": sm.state_machine_arn},
                    period=cdk.Duration.minutes(5),
                    statistic="Sum",
                ),
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                alarm_name=f"{name} pao",
                alarm_description=f"Step Functions {name} ima neuspješnu egzekuciju",
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )
            alarm.add_alarm_action(cw_actions.SnsAction(topic))
