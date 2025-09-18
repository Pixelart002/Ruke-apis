// --- Imports: Load required packages ---
const express = require('express');
const { MongoClient, ServerApiVersion } = require('mongodb');
const cors = require('cors');
const bcrypt = require('bcryptjs');

// --- Configuration & Initialization ---
const app = express();
const PORT = process.env.PORT || 8080; // Koyeb provides the PORT environment variable

// IMPORTANT: Securely load the database password from environment variables.
// We will set this in the Koyeb control panel, NOT here in the code.
const DB_PASSWORD = process.env.DB_PASSWORD;

if (!DB_PASSWORD) {
    console.error("FATAL ERROR: DB_PASSWORD environment variable not set.");
    process.exit(1); // Exit the application if the password is not found
}

const uri = `mongodb+srv://kyro:${DB_PASSWORD}@kyro.ov5daxu.mongodb.net/?retryWrites=true&w=majority&appName=Kyro`;

// --- Middleware ---
app.use(cors());      // Enable Cross-Origin Resource Sharing to allow frontend requests
app.use(express.json()); // Allow the server to understand JSON formatted request bodies

// --- Database Connection ---
const client = new MongoClient(uri, {
  serverApi: {
    version: ServerApiVersion.v1,
    strict: true,
    deprecationErrors: true,
  }
});

let usersCollection;

async function connectDB() {
  try {
    await client.connect();
    const db = client.db("yuku_mission_control");
    usersCollection = db.collection("users");
    console.log("✅ Connection to MongoDB: SECURE AND OPERATIONAL");
  } catch (err) {
    console.error("❌ MONGO CONNECTION FAILURE:", err);
    process.exit(1);
  }
}

// --- API Endpoints (Routes) ---

// Health check route to confirm the server is running
app.get('/', (req, res) => {
  res.status(200).json({ status: "YUKU Node.js Backend Operational" });
});

// Signup route for new user registration
app.post('/signup', async (req, res) => {
  const { fullname, email, password } = req.body;

  if (!fullname || !email || !password) {
    return res.status(400).json({ error: "Missing required fields" });
  }

  try {
    const existingUser = await usersCollection.findOne({ email: email.toLowerCase() });
    if (existingUser) {
      return res.status(409).json({ error: "Agent ID (Email) already registered" });
    }

    // Hash the password securely before storing
    const hashedPassword = await bcrypt.hash(password, 10); // 10 is the salt round

    await usersCollection.insertOne({
      fullname,
      email: email.toLowerCase(),
      password: hashedPassword,
    });

    res.status(201).json({ message: "Agent registration successful" });
  } catch (error) {
    console.error("Signup Error:", error);
    res.status(500).json({ error: "Internal server error during registration" });
  }
});

// Login route for user authentication
app.post('/login', async (req, res) => {
  const { email, password } = req.body;

  if (!email || !password) {
    return res.status(400).json({ error: "Missing email or password" });
  }

  try {
    const user = await usersCollection.findOne({ email: email.toLowerCase() });
    if (!user) {
      return res.status(401).json({ error: "Invalid credentials. Access denied." });
    }

    // Compare the provided password with the stored hashed password
    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) {
      return res.status(401).json({ error: "Invalid credentials. Access denied." });
    }

    res.status(200).json({
      message: "Authentication successful. Welcome, Agent.",
      user: { fullname: user.fullname, email: user.email },
    });
  } catch (error) {
    console.error("Login Error:", error);
    res.status(500).json({ error: "Internal server error during login" });
  }
});

// --- Start Server ---
// Connect to the database first, then start listening for requests.
connectDB().then(() => {
  app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
  });
});

