import express from "express";
import cors from "cors";
import session from "express-session";

const app = express();
const port = process.env.PORT || 3001;

app.use(express.json());
app.use(
  cors({
    origin: "http://localhost:5173",
    credentials: true,
  })
);

app.use(
  session({
    secret: "local-demo-secret",
    resave: false,
    saveUninitialized: true,
    cookie: {
      maxAge: 1000 * 60 * 30,
    },
  })
);

function requireLogin(req, res, next) {
  if (!req.session.user) {
    return res.status(401).json({ error: "not logged in" });
  }
  next();
}

app.get("/api/session", (req, res) => {
  req.session.user = { id: "u-1", email: "demo@example.com" };
  res.json({ user: req.session.user });
});

app.post("/api/account/email", requireLogin, (req, res) => {
  const nextEmail = String(req.body.email || "").trim();
  if (!nextEmail) {
    return res.status(400).json({ error: "email is required" });
  }

  req.session.user.email = nextEmail;
  res.json({ email: nextEmail });
});

app.listen(port, () => {
  console.log(`Simple API target listening on http://localhost:${port}`);
});
