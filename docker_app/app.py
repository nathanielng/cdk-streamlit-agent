#!/usr/bin/env python

# export AWS_DEFAULT_REGION="us-east-1"
# streamlit run agent_streamlit_app.py --server.runOnSave True --server.port 8501

# curl -LO https://raw.githubusercontent.com/aws-samples/amazon-bedrock-workshop/refs/heads/main/05_Agents/agent.py
# curl -LO https://raw.githubusercontent.com/nathanielng/cdk-streamlit-agent/refs/heads/main/docker_app/config_file.py

# mkdir -p utils && cd utils
# curl -LO https://raw.githubusercontent.com/nathanielng/cdk-streamlit-agent/refs/heads/main/docker_app/utils/auth.py

import boto3
import os
import logging
import json
import uuid
import streamlit as st

from agent import invoke_agent_helper
from utils.auth import Auth
from config_file import Config

# ID of Secrets Manager containing cognito parameters
secrets_manager_id = Config.SECRETS_MANAGER_ID

# ID of the AWS region in which Secrets Manager is deployed
region = Config.DEPLOYMENT_REGION

# Initialise CognitoAuthenticator
authenticator = Auth.get_authenticator(secrets_manager_id, region)

# Authenticate user, and stop here if not logged in
is_logged_in = authenticator.login()
if not is_logged_in:
    st.stop()


def logout():
    authenticator.logout()


with st.sidebar:
    st.text(f"Welcome,\n{authenticator.get_username()}")
    st.button("Logout", "logout_btn", on_click=logout)


# ----- Logging -----
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ----- Setup -----
session_id = str(uuid.uuid1())
logger.info(f"Session ID: {session_id}")

# ----- SSM Setup -----
ssm = boto3.client('ssm')
agent_id = ssm.get_parameter(Name='/agents/AGENT_ID').get('Parameter').get('Value')
alias_id = ssm.get_parameter(Name='/agents/ALIAS_ID').get('Parameter').get('Value')

lambda_iam_role = ssm.get_parameter(Name='/agents/LAMBDA_IAM_ROLE').get('Parameter').get('Value')
lambda_iam_role = json.loads(lambda_iam_role)

agent_role = ssm.get_parameter(Name='/agents/AGENT_ROLE').get('Parameter').get('Value')
agent_role = json.loads(agent_role)

# lambda_function = json.loads(lambda_function)
# agent_action_group_response = json.loads(agent_action_group_response)
# agent_functions = json.loads(agent_functions)

# agent_name = ssm.get_parameter(Name='/agents/AGENT_NAME').get('Parameter').get('Value')
# suffix = ssm.get_parameter(Name='/agents/SUFFIX').get('Parameter').get('Value')
# region = ssm.get_parameter(Name='/agents/REGION').get('Parameter').get('Value')
# agent_foundation_model = ssm.get_parameter(Name='/agents/AGENT_FOUNDATION_MODEL').get('Parameter').get('Value')
# account_id = ssm.get_parameter(Name='/agents/ACCOUNT_ID').get('Parameter').get('Value')
# alias_id = ssm.get_parameter(Name='/agents/ALIAS_ID').get('Parameter').get('Value')
# lambda_function = ssm.get_parameter(Name='/agents/LAMBDA_FUNCTION').get('Parameter').get('Value')
# lambda_function_name = ssm.get_parameter(Name='/agents/LAMBDA_FUNCTION_NAME').get('Parameter').get('Value')
# agent_action_group_response = ssm.get_parameter(Name='/agents/AGENT_ACTION_GROUP_RESPONSE').get('Parameter').get('Value')
# agent_functions = ssm.get_parameter(Name='/agents/AGENT_FUNCTIONS').get('Parameter').get('Value')
table_name = ssm.get_parameter(Name='/agents/TABLE_NAME').get('Parameter').get('Value')


# ----- DynamoDB -----
def get_recent_bookings(table_name):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    response = table.scan(
        Limit=3
    )
    items = response.get('Items', [])
    return items

def clear_bookings(table_name):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    response = table.scan()
    items = response.get('Items', [])
    for item in items:
        table.delete_item(
            Key={
                'booking_id': item['booking_id']
            }
        )

# ----- Streamlit UI -----
st.title("Restaurant Booking Assistant")

def update_sidebar():
    with st.sidebar:
        st.header("Recent Bookings")
        recent_bookings = get_recent_bookings(table_name)
        if recent_bookings:
            for booking in recent_bookings:
                st.write("---")
                txt = []
                for key, value in booking.items():
                    txt.append(f"**{key}:** {value}")
                st.write('\n\n'.join(txt))
        else:
            st.write("No recent bookings found")

        st.button("Clear Bookings", on_click=clear_bookings, args=(table_name,))


def main():
    st.write("Enter your booking request")
    query = st.text_area(
        label="Include your name, number of people, date, and time:",
        value="Hi, I am Anna. I want to create a booking for 2 people, at 8pm on the 5th of May 2025.",
        height=80
    )

    if st.button("Submit"):
        with st.spinner('Processing your request...'):
            answer = invoke_agent_helper(query, session_id, agent_id, alias_id)
            st.markdown(answer)
    update_sidebar()



if __name__ == '__main__':
    main()
