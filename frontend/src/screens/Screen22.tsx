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

const Screen22IdeaChecker = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Research Idea Checker">
      <div className="max-w-3xl mx-auto text-center mt-10">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-50 mb-6">
          <Lightbulb className="w-8 h-8 text-[#00502F]" />
        </div>
        <h2 className="text-3xl font-bold text-slate-900 mb-4">Has your idea been explored?</h2>
        <p className="text-slate-600 mb-10 text-lg">Describe your proposed research. Our AI will check the OAU repository for similar completed projects to help you ensure novelty.</p>
        
        <Card className="p-2 shadow-md mb-6">
          <textarea 
            placeholder="E.g., I want to use convolutional neural networks to detect malaria parasites in blood smears using a mobile phone attachment..."
            className="w-full h-40 p-4 border-none resize-none focus:ring-0 text-slate-800 placeholder-slate-400"
          ></textarea>
        </Card>
        
        <Button size="lg" className="px-8 py-3 text-lg" onClick={() => navigate('idea-similarity')}>Analyze My Idea</Button>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen22IdeaChecker;
