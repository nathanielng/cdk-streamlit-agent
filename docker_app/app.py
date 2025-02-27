#!/usr/bin/env python

# export AWS_DEFAULT_REGION="us-east-1"
# streamlit run agent_streamlit_app.py --server.runOnSave True --server.port 8501

# curl -LO https://raw.githubusercontent.com/aws-samples/amazon-bedrock-workshop/refs/heads/main/05_Agents/agent.py
# curl -LO https://raw.githubusercontent.com/nathanielng/cdk-streamlit-agent/refs/heads/main/docker_app/config_file.py

# mkdir -p utils && cd utils
# curl -LO https://raw.githubusercontent.com/nathanielng/cdk-streamlit-agent/refs/heads/main/docker_app/utils/auth.py

import base64
import boto3
import os
import logging
import json
import uuid
import streamlit as st

from agent import invoke_agent_helper
from config_file import Config
from utils.auth import Auth

# Set Streamlit to wide mode
st.set_page_config(layout="wide")

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

iam_client = boto3.client('iam')
bedrock_agent_client = boto3.client('bedrock-agent')
bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime')
s3_client = boto3.client('s3')


# ----- SSM Parameter Setup -----
ssm = boto3.client('ssm')
agent_foundation_model = ssm.get_parameter(Name='/agents/AGENT_FOUNDATION_MODEL').get('Parameter').get('Value')
agent_id = ssm.get_parameter(Name='/agents/AGENT_ID').get('Parameter').get('Value')
alias_id = ssm.get_parameter(Name='/agents/ALIAS_ID').get('Parameter').get('Value')
kb_id = ssm.get_parameter(Name='/agents/KB_ID').get('Parameter').get('Value')
region = ssm.get_parameter(Name='/agents/REGION').get('Parameter').get('Value')

lambda_iam_role = ssm.get_parameter(Name='/agents/LAMBDA_IAM_ROLE').get('Parameter').get('Value')
lambda_iam_role = json.loads(lambda_iam_role)

agent_role = ssm.get_parameter(Name='/agents/AGENT_ROLE').get('Parameter').get('Value')
agent_role = json.loads(agent_role)

table_name = ssm.get_parameter(Name='/agents/TABLE_NAME').get('Parameter').get('Value')
bucket_name = ssm.get_parameter(Name='/agents/BUCKET_NAME').get('Parameter').get('Value')

# agent_name = ssm.get_parameter(Name='/agents/AGENT_NAME').get('Parameter').get('Value')
# suffix = ssm.get_parameter(Name='/agents/SUFFIX').get('Parameter').get('Value')
# account_id = ssm.get_parameter(Name='/agents/ACCOUNT_ID').get('Parameter').get('Value')
# alias_id = ssm.get_parameter(Name='/agents/ALIAS_ID').get('Parameter').get('Value')
# lambda_function = ssm.get_parameter(Name='/agents/LAMBDA_FUNCTION').get('Parameter').get('Value')
# lambda_function_name = ssm.get_parameter(Name='/agents/LAMBDA_FUNCTION_NAME').get('Parameter').get('Value')
# agent_action_group_response = ssm.get_parameter(Name='/agents/AGENT_ACTION_GROUP_RESPONSE').get('Parameter').get('Value')
# agent_functions = ssm.get_parameter(Name='/agents/AGENT_FUNCTIONS').get('Parameter').get('Value')

# agent_action_group_response = json.loads(agent_action_group_response)
# lambda_function = json.loads(lambda_function)
# agent_functions = json.loads(agent_functions)


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
st.title("🍽️ Restaurant Booking Assistant")

def update_sidebar():
    with st.sidebar:
        st.session_state.name = st.text_input(label='Name')
        st.header("📋 Recent Bookings")
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

        st.button("🗑️ Clear Bookings", on_click=clear_bookings, args=(table_name,))


def tab_agent():
    st.write("ℹ️ Enter a booking request with your name, number of people, date, and time, or ask a question about the menu")

    st.markdown("**Examples**:\n- Hi, I am Anna. I want to create a booking for 2 people, at 8pm on the 5th of May 2025.\n- I want to delete the booking.\n- Could you get the details for the last booking created?\n- What do you have for kids that don't like fries?\n- I am allergic to shrimps. What can I eat at this restaurant?\n- What are the desserts on the adult menu?\n- ¿Podrías reservar una mesa para dos 25/07/2025 a las 19:30")

    query = st.text_area(
        label="✨ Enter your query below:",
        value="Hi, I am Anna. I want to create a booking for 2 people, at 8pm on the 5th of May 2025.",
        height=80
    )

    if st.button("📤 Submit", key="booking_request"):
        with st.spinner('Processing your request...'):
            if st.session_state.name:
                session_state = {
                    "promptSessionAttributes": {
                        "name": st.session_state.name
                    }
                }
                answer = invoke_agent_helper(query, session_id, agent_id, alias_id, session_state=session_state)
            else:
                answer = invoke_agent_helper(query, session_id, agent_id, alias_id)                
            st.markdown(answer)
    update_sidebar()


def download_if_not_exists(bucket_name, filename):
    localfilepath = filename
    if not os.path.isfile(localfilepath):
        try:
            s3_client.download_file(
                Bucket = bucket_name,
                Key = filename,
                Filename = localfilepath
            )
        except Exception as e:
            st.error(f"Error downloading {filename} from s3://{bucket_name}/{filename}: {e}")
            return False
    return True


def display_pdf(filename):
    localfilepath = filename
    if not os.path.isfile(localfilepath):
        st.error(f"File {filename} not found")
    else:
        with open(localfilepath, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)


def tab_knowledgebase():
    st.write("📝 Ask questions about the menu")

    st.markdown("**Example questions**: Which are the 5 mains available in the childrens menu? What is in the children's menu? Which of those options are vegetarian?")
 
    menu_query = st.text_area(
        label="✨ Question",
        value="What is in the children's menu?",
        height=80,
        key="menu_query"
    )

    if st.button("📤 Submit", key="kb_submit"):
        with st.spinner('Processing your request...'):
            response = bedrock_agent_runtime_client.retrieve_and_generate(
            input={
                "text": menu_query
            },
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    'knowledgeBaseId': kb_id,
                    "modelArn": "arn:aws:bedrock:{}::foundation-model/{}".format(region, agent_foundation_model),
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {
                            "numberOfResults":5
                        } 
                    }
                }
            }
        )
        answer = response['output']['text']
        st.write(answer)

    download_if_not_exists(bucket_name, "Restaurant_Childrens_Menu.pdf")
    download_if_not_exists(bucket_name, "Restaurant_Dinner_Menu.pdf")
    download_if_not_exists(bucket_name, "Restaurant_week_specials.pdf")

    menu_selection = st.selectbox(
        label='Select a menu',
        options = [
            "🍽️ Children's Menu",
            "🍽️ Dinner Menu",
            "🍽️ Week Specials"
        ]
    )

    if menu_selection == "🍽️ Children's Menu":
        display_pdf("Restaurant_Childrens_Menu.pdf")
    elif menu_selection == "🍽️ Dinner Menu":
        display_pdf("Restaurant_Dinner_Menu.pdf")
    elif menu_selection == "🍽️ Week Specials":
        display_pdf("Restaurant_week_specials.pdf")
 


def main():
    tab1, tab2 = st.tabs(["Bookings & Menu Queries", "Menu"])

    with tab1:
        tab_agent()

    with tab2:
        tab_knowledgebase()



if __name__ == '__main__':
    if 'name' not in st.session_state:
        st.session_state.name = ''

    main()
