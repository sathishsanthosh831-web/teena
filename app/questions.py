import random

# (question, [options], index of correct option, explanation)
APTITUDE = [
    ("A train 120 m long passes a pole in 6 s. Its speed in km/h is?", ["54", "72", "60", "80"], 1, "120/6 = 20 m/s = 72 km/h."),
    ("If 20% of a number is 45, the number is?", ["180", "225", "200", "250"], 1, "45 / 0.2 = 225."),
    ("Next in series: 2, 6, 12, 20, 30, ?", ["40", "42", "44", "38"], 1, "Differences 4,6,8,10,12 so 30+12 = 42."),
    ("Simple interest on Rs 5000 at 8% for 3 years?", ["1000", "1200", "1400", "1600"], 1, "5000*8*3/100 = 1200."),
    ("A can do a job in 10 days, B in 15 days. Together they take?", ["5", "6", "7", "8"], 1, "1/10 + 1/15 = 1/6, so 6 days."),
    ("Average of 5 numbers is 20. If one number is removed the average becomes 18. Removed number?", ["24", "28", "26", "30"], 1, "100 - 72 = 28."),
    ("Ratio of boys to girls is 3:2. If there are 30 boys, total students?", ["45", "50", "55", "60"], 1, "30 boys = 3 parts, so 10 per part, total 50."),
    ("Cost price 400, selling price 500. Profit %?", ["20", "25", "30", "15"], 1, "100/400 = 25%."),
    ("How many ways can 4 people sit in a row?", ["12", "24", "16", "48"], 1, "4! = 24."),
    ("Probability of getting a head in one coin toss?", ["1/4", "1/2", "1", "0"], 1, "Two equally likely outcomes."),
    ("Find odd one out: 8, 27, 64, 100, 125", ["8", "27", "100", "125"], 2, "All others are perfect cubes."),
    ("If letters are valued A=1, B=2... then CAT = 24. What is BAT?", ["23", "22", "21", "25"], 0, "B+A+T = 2+1+20 = 23."),
    ("Speed 60 km/h. Distance covered in 45 minutes?", ["40 km", "45 km", "50 km", "30 km"], 1, "60 * 0.75 = 45 km."),
    ("Square root of 1764?", ["42", "44", "46", "38"], 0, "42*42 = 1764."),
    ("A number is doubled and then increased by 10 to get 50. The number is?", ["15", "20", "25", "30"], 1, "(50-10)/2 = 20."),
]

# role -> list of (question, keywords expected in a good answer)
INTERVIEW = {
    "python-developer": [
        ("What is the difference between a list and a tuple in Python?", ["mutable", "immutable", "tuple", "list", "hashable", "memory"]),
        ("Explain how Python manages memory.", ["garbage", "reference", "counting", "heap", "gc"]),
        ("What are decorators and where would you use them?", ["function", "wrap", "decorator", "logging", "auth", "@"]),
        ("What is the difference between a process and a thread? What is the GIL?", ["gil", "thread", "process", "parallel", "concurrency", "lock"]),
    ],
    "web-developer": [
        ("Explain the CSS box model.", ["margin", "padding", "border", "content"]),
        ("What is the difference between var, let and const?", ["scope", "hoisting", "block", "reassign", "const"]),
        ("How does a browser render a web page?", ["dom", "css", "render", "parse", "javascript", "html"]),
        ("What is REST and how do you call an API from the frontend?", ["fetch", "http", "get", "post", "json", "endpoint"]),
    ],
    "data-analyst": [
        ("What is the difference between INNER JOIN and LEFT JOIN?", ["inner", "left", "matching", "null", "rows", "join"]),
        ("How would you handle missing values in a dataset?", ["drop", "impute", "mean", "median", "null", "missing"]),
        ("Explain mean, median and mode. When is median better?", ["outlier", "mean", "median", "mode", "skew"]),
        ("What makes a good dashboard?", ["audience", "kpi", "clear", "chart", "filter", "simple"]),
    ],
    "java-developer": [
        ("What are the four pillars of OOP?", ["encapsulation", "inheritance", "polymorphism", "abstraction"]),
        ("Difference between an abstract class and an interface?", ["abstract", "interface", "implement", "extend", "multiple", "method"]),
        ("How does garbage collection work in Java?", ["heap", "garbage", "jvm", "unreachable", "memory", "object"]),
        ("What is the difference between == and equals()?", ["reference", "equals", "value", "string", "object"]),
    ],
}


def pick_aptitude(n=5):
    ids = random.sample(range(len(APTITUDE)), n)
    return ids


def score_answer(answer, keywords):
    low = answer.lower()
    words = len(answer.split())
    hit = [k for k in keywords if k in low]
    miss = [k for k in keywords if k not in low]
    keyword_part = round(70 * len(hit) / len(keywords))
    length_part = 30 if words >= 40 else round(30 * words / 40)
    score = min(100, keyword_part + length_part)
    feedback = []
    if words < 40:
        feedback.append("Answer is short. Aim for 40+ words with an example.")
    if miss:
        feedback.append("Try to mention: " + ", ".join(miss[:4]) + ".")
    if not feedback:
        feedback.append("Great answer. Covers the key points.")
    return score, hit, feedback
