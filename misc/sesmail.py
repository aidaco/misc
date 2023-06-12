import boto3


class SES:
    def __init__(self, source, client=None):
        self.source = source
        self.client = client or boto3.client("ses")

    def send(self, dest, sub, body):
        response = self.client.send_email(
            **{
                "Source": self.source,
                "Destination": {"ToAddresses": [dest]},
                "Message": {
                    "Subject": {"Data": sub},
                    "Body": {"Text": {"Data": body}, "Html": {"Data": body}},
                },
            }
        )
        return response["MessageId"]
