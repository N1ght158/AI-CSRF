import React, { useEffect, useState } from "react";

const API_BASE = "http://localhost:3001";

export default function App() {
  const [email, setEmail] = useState("demo@example.com");
  const [message, setMessage] = useState("Not submitted yet");

  useEffect(() => {
    fetch(`${API_BASE}/api/session`, {
      credentials: "include",
    }).catch(() => setMessage("Session initialization failed"));
  }, []);

  async function submitEmail(event) {
    event.preventDefault();
    const response = await fetch(`${API_BASE}/api/account/email`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email }),
    });

    if (!response.ok) {
      setMessage("Submit failed");
      return;
    }

    const data = await response.json();
    setMessage(`Email changed to ${data.email}`);
  }

  return (
    <main style={{ maxWidth: 520, margin: "40px auto", fontFamily: "sans-serif" }}>
      <h1>Simple Web Target</h1>
      <p>This page sends a cookie-based email update request.</p>
      <form onSubmit={submitEmail}>
        <label>
          New email
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            style={{ display: "block", width: "100%", margin: "8px 0" }}
          />
        </label>
        <button type="submit">Submit</button>
      </form>
      <p>{message}</p>
    </main>
  );
}
