import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
from constructs import Construct


class GoldStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        lambda_sg: ec2.SecurityGroup,
        bucket: s3.Bucket,
        ec2_private_ip: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.metrics_calculator = lambda_.DockerImageFunction(
            self,
            "MetricsCalculator",
            code=lambda_.DockerImageCode.from_image_asset(
                "../lambdas/gold/metrics_calculator"
            ),
            vpc=vpc,
            security_groups=[lambda_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            timeout=cdk.Duration.minutes(15),
            memory_size=1024,
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "BRONZE_HN_PREFIX": "bronze/hacker-news",
                "BRONZE_TWITTER_KEY": "bronze/twitter/covid_tweets.csv",
                "SILVER_PREFIX": "silver",
                "GOLD_PREFIX": "gold",
            },
        )

        bucket.grant_read(self.metrics_calculator, "bronze/hacker-news/*")
        bucket.grant_read(self.metrics_calculator, "bronze/twitter/*")
        bucket.grant_read(self.metrics_calculator, "silver/*")
        bucket.grant_read_write(self.metrics_calculator, "gold/*")

        self.s3_to_postgres = lambda_.DockerImageFunction(
            self,
            "S3ToPostgres",
            code=lambda_.DockerImageCode.from_image_asset(
                "../lambdas/gold/s3_to_postgres"
            ),
            vpc=vpc,
            security_groups=[lambda_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            timeout=cdk.Duration.minutes(10),
            memory_size=512,
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "GOLD_PREFIX": "gold",
                "PG_HOST": ec2_private_ip,
            },
        )

        bucket.grant_read(self.s3_to_postgres, "gold/*")

        metrics_task = tasks.LambdaInvoke(
            self, "RunMetricsCalculator", lambda_function=self.metrics_calculator
        )
        metrics_task.add_retry(
            max_attempts=2,
            interval=cdk.Duration.seconds(30),
            backoff_rate=2,
            errors=["States.TaskFailed", "Lambda.ServiceException"],
        )
        metrics_task.add_catch(
            sfn.Pass(self, "MetricsCalculatorFailed"),
            errors=["States.ALL"],
            result_path="$.metrics_error",
        )

        sync_task = tasks.LambdaInvoke(
            self, "RunS3ToPostgres", lambda_function=self.s3_to_postgres
        )
        sync_task.add_retry(
            max_attempts=2,
            interval=cdk.Duration.seconds(30),
            backoff_rate=2,
            errors=["States.TaskFailed", "Lambda.ServiceException"],
        )
        sync_task.add_catch(
            sfn.Pass(self, "S3ToPostgresFailed"),
            errors=["States.ALL"],
            result_path="$.sync_error",
        )

        state_machine = sfn.StateMachine(
            self,
            "GoldStateMachine",
            state_machine_name="gold-pipeline",
            definition_body=sfn.DefinitionBody.from_chainable(
                metrics_task.next(sync_task)
            ),
            timeout=cdk.Duration.minutes(30),
        )

        rule = events.Rule(
            self,
            "DailyMetricsTrigger",
            schedule=events.Schedule.cron(hour="3", minute="0"),
            description="Daily trigger for gold pipeline at 3am UTC",
        )
        rule.add_target(targets.SfnStateMachine(state_machine))
