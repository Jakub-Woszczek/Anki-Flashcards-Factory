from openai import OpenAI

class ChadGPT:
    def __init__(self):
        self.client = OpenAI()
        pass

    def get_answer(self,input):
        print(f"input: {input}")
        response = self.client.responses.create(
            model="gpt-4o-mini",
            input=input
        )
        
        return response.output_text