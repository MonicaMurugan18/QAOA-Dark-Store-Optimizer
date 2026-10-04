import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";
import Stores from "./pages/Stores";
import Products from "./pages/Products";
import Demand from "./pages/Demand";
import History from "./pages/History";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public landing page. Standalone -- it has its own nav and footer
            rather than the optimizer's sidebar shell. */}
        <Route path="/" element={<Landing />} />

        {/* The existing optimizer, unchanged, now under /optimizer.
            Every inner page keeps the path it already had. */}
        <Route element={<Layout />}>
          <Route path="/optimizer" element={<Dashboard />} />
          <Route path="/stores" element={<Stores />} />
          <Route path="/products" element={<Products />} />
          <Route path="/demand" element={<Demand />} />
          <Route path="/history" element={<History />} />
        </Route>

        {/* Anything unknown goes to the landing page. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
