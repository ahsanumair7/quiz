import asyncio
import json
import os
from src.agent.capability import MatchingCapability
from src.main import AgentWorker
from src.agent.capability_worker import CapabilityWorker

QUIZ_INTRO_PROMPT = "Welcome to the Quiz App! We will ask you {num_questions} questions on {category}."
QUIZ_CATEGORY = "General Knowledge"  # Changeable from code
NUM_QUESTIONS = 3  # Changeable from code
FEEDBACK_PROMPT = "Your answer is {feedback}."
FINAL_PROMPT = "You got {correct_count} out of {num_questions} correct! Thanks for playing the quiz!"

GENERATE_QUESTIONS_PROMPT = (
    """Generate {num_questions} multiple-choice questions on the category {category}. 
    Each question should have four answer choices, clearly labeled A, B, C, and D, and specify the correct answer.
    Format the response as a JSON list where each element has 'question', 'choices', and 'correct_answer'."""
)

class QuizCapabilityCapability(MatchingCapability):
    worker: AgentWorker = None
    capability_worker: CapabilityWorker = None
    quiz_questions: list = []

    @classmethod
    def register_capability(cls) -> "MatchingCapability":
        with open(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"),
        ) as file:
            data = json.load(file)
        return cls(
            unique_name=data["unique_name"],
            matching_hotwords=data["matching_hotwords"],
        )

    async def get_gpt_response(self, prompt: str, history: list = []) -> str:
        # Replace with actual GPT call logic
        response = self.capability_worker.text_to_text_response(prompt, history)
        return response

    async def generate_quiz_questions(self):
        """
        Generate quiz questions using GPT based on the chosen category and number of questions.
        """
        try:
            question_prompt = GENERATE_QUESTIONS_PROMPT.format(num_questions=NUM_QUESTIONS, category=QUIZ_CATEGORY)
            question_prompt += " Here is an example of the expected format: " + str([
                {"question": "What is the capital of France?", "choices": ["A. London", "B. Paris", "C. Berlin", "D. Madrid"], "correct_answer": "B. Paris"},
                {"question": "What is 2 + 2?", "choices": ["A. 3", "B. 4", "C. 5", "D. 6"], "correct_answer": "B. 4"}
            ]) + " Only output JSON and nothing else."

            # Make sure to await the GPT response
            gpt_response = await self.get_gpt_response(question_prompt)

            # Parse the GPT response as JSON
            self.quiz_questions = json.loads(gpt_response)
        except json.JSONDecodeError:
            # Handle JSON error and retry generating questions
            await self.capability_worker.speak("Sorry, there was an error generating quiz questions. Retrying...")
            await self.generate_quiz_questions()

    async def ask_question(self, question_data: dict):
        """
        Asks a question to the user, processes their response, and checks if the answer is correct.
        Exits if the user wants to switch capabilities or exit the quiz.
        """
        question_prompt = question_data["question"] + " " + " ".join(question_data["choices"])
        self.worker.editor_logging_handler.info(question_prompt)
        await self.capability_worker.speak(question_prompt)

        self.worker.editor_logging_handler.info("Expected Answer: %s" % question_data['correct_answer'])

        # Get user response
        user_answer = await self.capability_worker.user_response()

        # Check if the user wants to exit or switch capabilities
        if "exit" in user_answer.lower() or "switch to" in user_answer.lower():
            await self.capability_worker.speak("Exiting the quiz. See you next time!")
            self.capability_worker.resume_normal_flow()  # Ensure to stop the quiz and resume normal flow
            return None  # Indicate the quiz should exit

        # Send GPT prompt to check if the answer is correct
        answer_check_prompt = f"Question was: '{question_prompt}' its answer is '{question_data['correct_answer']}'\n Here is the user's response '{user_answer}', Is the user's response correct?" \
                            "Consider synonyms or similar variations when evaluating user's response, use your intelligence in evaluating the answer, always include yes or no in your answer."
        self.worker.editor_logging_handler.info(answer_check_prompt)
        gpt_response = await self.get_gpt_response(answer_check_prompt)
        self.worker.editor_logging_handler.info(gpt_response)

        # If GPT determines the answer is correct
        if "yes" in gpt_response.lower():
            return True
        return False

    async def run_quiz(self):
        """
        Main function to run the quiz.
        """
        correct_count = 0
        await self.capability_worker.speak(QUIZ_INTRO_PROMPT.format(num_questions=NUM_QUESTIONS, category=QUIZ_CATEGORY))

        # Step 1: Generate quiz questions dynamically using GPT
        await self.generate_quiz_questions()

        # Step 2: Ask each question and check answers
        for i, question in enumerate(self.quiz_questions[:NUM_QUESTIONS]):
            is_correct = await self.ask_question(question)

            if is_correct is None:
                break

            feedback = "correct" if is_correct else "incorrect"
            await self.capability_worker.speak(FEEDBACK_PROMPT.format(feedback=feedback))

            if is_correct:
                correct_count += 1

        # Step 3: Provide final score
        if is_correct is not None:
            await self.capability_worker.speak(FINAL_PROMPT.format(correct_count=correct_count, num_questions=NUM_QUESTIONS))
        self.capability_worker.resume_normal_flow()

    def call(self, worker: AgentWorker):
        # Initialize the worker and capability worker
        self.worker = worker
        self.capability_worker = CapabilityWorker(self.worker)

        # Start the quiz functionality
        asyncio.create_task(self.run_quiz())
