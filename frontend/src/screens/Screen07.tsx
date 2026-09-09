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

const Screen07AdvancedSearch = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Advanced Search">
      <div className="max-w-3xl mx-auto bg-white p-8 rounded-xl border border-slate-200 shadow-sm">
        <h2 className="text-2xl font-bold text-slate-900 mb-6">Build Query</h2>
        <form className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Input label="Exact Phrase" placeholder='e.g. "neural networks"' />
            <Input label="Has all these words" placeholder="e.g. crop yield nigeria" />
            <div className="flex flex-col space-y-1.5">
              <label className="text-sm font-medium text-slate-700">Department</label>
              <select className="px-3 py-2 border border-slate-300 rounded-md bg-white">
                <option>All Departments</option>
                <option>Computer Science</option>
              </select>
            </div>
            <Input label="Author/Supervisor" placeholder="Name" />
            <Input label="Methodology Used" placeholder="e.g. Qualitative, Regression" />
            <Input label="Dataset referenced" placeholder="e.g. ImageNet, Local Survey" />
          </div>
          <div className="pt-6 border-t border-slate-200 flex justify-end space-x-4">
            <Button variant="ghost" type="button">Clear Fields</Button>
            <Button onClick={() => navigate('search-results')} type="button">Search Repository</Button>
          </div>
        </form>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen07AdvancedSearch;
