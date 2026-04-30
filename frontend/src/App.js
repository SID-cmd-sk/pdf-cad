import { BrowserRouter, Routes, Route, Link, useLocation } from "react-router-dom";
import "@/App.css";
import "@/index.css";
import { Toaster } from "@/components/ui/sonner";
import Home from "@/pages/Home";
import JobView from "@/pages/JobView";
import Rules from "@/pages/Rules";
import About from "@/pages/About";

const Nav = () => {
    const loc = useLocation();
    const active = (p) => (loc.pathname === p ? "nav-link active" : "nav-link");
    return (
        <div className="topbar" data-testid="app-topbar">
            <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
                <span className="brand">CAD/ASSIST</span>
                <span className="brand-sub">Local Vector Reconstruction Engine</span>
            </div>
            <div style={{ flex: 1 }} />
            <Link to="/" className={active("/")} data-testid="nav-jobs">Jobs</Link>
            <Link to="/rules" className={active("/rules")} data-testid="nav-rules">Learning</Link>
            <Link to="/about" className={active("/about")} data-testid="nav-about">About</Link>
        </div>
    );
};

function App() {
    return (
        <div className="App">
            <BrowserRouter>
                <div className="app-shell">
                    <Nav />
                    <Routes>
                        <Route path="/" element={<Home />} />
                        <Route path="/job/:id" element={<JobView />} />
                        <Route path="/rules" element={<Rules />} />
                        <Route path="/about" element={<About />} />
                    </Routes>
                </div>
                <Toaster theme="dark" position="bottom-right" />
            </BrowserRouter>
        </div>
    );
}

export default App;
