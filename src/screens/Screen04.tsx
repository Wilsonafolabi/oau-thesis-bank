import React, { useState, useEffect, useContext, createContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, BookOpen, Users, Cpu, FileText, ChevronRight, Lock, Unlock, Mail, Settings,
  LogOut, Bell, MessageSquare, Activity, BarChart2, PlusCircle, CheckCircle, AlertTriangle,
  Download, Bookmark, Share2, Filter, MoreVertical, X, Menu, Home, Grid, Lightbulb,
  FileSearch, UserPlus, Shield, Check, FileUp, Database, GitBranch, ArrowRight, ArrowLeft,
  MessageCircle, Link as LinkIcon, ThumbsUp, Send, PieChart, TrendingUp, Search as SearchIcon,
  ShieldAlert, Settings2, Sliders, ChevronDown, Book, User, Calendar
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart as RePieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  theme, MOCK_THESES, MOCK_USERS, MOCK_MESSAGES, useAppRouter,
  Button, Input, Card, Badge, PublicLayout, AuthenticatedLayout, AuthContainer,
  ThesisCard, UploadWizardNav, pageVariants, listVariants, itemVariants
} from '../components/shared';

const Screen04PasswordReset = () => {
  const { navigate } = useAppRouter();
  const [sent, setSent] = useState(false);
  return (
    <AuthContainer title="Reset Password" subtitle={sent ? "Check your email" : "Enter your email to receive a reset link"}>
      {!sent ? (
        <form className="space-y-6" onSubmit={(e) => { e.preventDefault(); setSent(true); }}>
          <Input label="OAU Email" type="email" placeholder="student@student.oauife.edu.ng" />
          <Button type="submit" className="w-full">Send Reset Link</Button>
          <Button variant="ghost" className="w-full" onClick={() => navigate('login')}>Back to login</Button>
        </form>
      ) : (
        <div className="text-center space-y-6">
          <Mail className="mx-auto h-12 w-12 text-[#00502F] opacity-50" />
          <p className="text-sm text-slate-600">We've sent a password reset link to your email. Please check your inbox.</p>
          <Button className="w-full" onClick={() => navigate('login')}>Return to Login</Button>
        </div>
      )}
    </AuthContainer>
  );
};

export default Screen04PasswordReset;
