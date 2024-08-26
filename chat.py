from litellm import completion
import memory

BASE_PROMPT = ""

conversation = []
while True:
    user_input = input("User> ")
    conversation.append(
        {
            "role": "user",
            "content": user_input,
        }
    )
    memory.save(user_input)
    response = completion(model="groq/llama-3.1-70b-versatile", messages=conversation)
    model_output = response.choices[0].message.content
    conversation.append(
        {
            "role": "assistant",
            "content": model_output,
        }
    )
    print(f"Bot> {model_output}")
